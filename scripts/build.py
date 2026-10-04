#!/usr/bin/env python3
"""Pinned baseline restore and explicit, phase-gated build helpers."""
import argparse, datetime, hashlib, json, os, pathlib, re, shutil, subprocess, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
LOCK=json.loads((ROOT/'upstream.lock.json').read_text())
def run(*args, cwd=None):
    subprocess.run(args,cwd=cwd,check=True)
def restore(name):
    available=subprocess.run(['git','cat-file','-e',LOCK['baseline_commit']+'^{commit}'],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
    if not available:
        bundle=ROOT/'barony-public-upstream.bundle'
        if not bundle.is_file():
            raise RuntimeError('Pinned baseline is absent; fetch project history or supply its verified public upstream bundle')
        run('git','bundle','verify',str(bundle),cwd=ROOT)
        run('git','fetch',str(bundle),'refs/heads/bootstrap/public-upstream:refs/remotes/bootstrap/baseline',cwd=ROOT)
    dest=ROOT/'.work'/name
    if dest.exists():
        verify(dest); return dest
    dest.parent.mkdir(parents=True,exist_ok=True)
    run('git','worktree','add','--detach',str(dest),LOCK['baseline_commit'],cwd=ROOT)
    verify(dest); return dest

def verify(dest):
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=dest,text=True).strip()
    status=subprocess.check_output(['git','status','--porcelain'],cwd=dest,text=True).strip()
    if sha!=LOCK['baseline_commit'] or status:
        raise RuntimeError('Expected clean pinned snapshot; do not overwrite existing work')

def validate_baseline_evidence(path, root=ROOT, baseline=None):
    """A marker file is never sufficient proof of a successful runtime baseline.

    Evidence is an auditable human/QA attestation, not a cryptographic guarantee
    that somebody played the game. Referenced logs must exist and match hashes.
    """
    baseline = baseline or LOCK['baseline_commit']
    try:
        record=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(record, dict) or record.get('schema_version') != 1:
            raise ValueError('unsupported evidence schema')
        if record.get('baseline_commit') != baseline:
            raise ValueError('baseline revision mismatch')
        if record.get('evidence_kind') != 'human_attestation':
            raise ValueError('explicit independent runtime attestation required')
        observer=record.get('observer', {})
        if observer.get('role') not in ('QA_AGENT', 'PLAYTEST_AGENT', 'HUMAN') or not isinstance(observer.get('id'),str) or not observer['id'].strip() or observer['id']==record.get('producer'):
            raise ValueError('runtime observer must be independent from build producer')
        recorded=datetime.datetime.fromisoformat(record.get('recorded_at', '').replace('Z', '+00:00'))
        if recorded.tzinfo is None or recorded.utcoffset()!=datetime.timedelta(0) or recorded > datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=5):
            raise ValueError('invalid UTC timestamp')
        def checked_file(entry):
            relative=entry.get('path', '')
            if not isinstance(relative,str) or not relative or pathlib.Path(relative).is_absolute():
                raise ValueError('invalid manifest path')
            target=(root/relative).resolve(); target.relative_to(root.resolve())
            if not target.is_file() or target.stat().st_size==0 or hashlib.sha256(target.read_bytes()).hexdigest()!=entry.get('sha256'):
                raise ValueError('manifest subject missing or changed')
            return target
        binary=record.get('binary', {})
        checked_file(binary)
        marker_entry=record.get('profile_marker', {})
        marker=json.loads(checked_file(marker_entry).read_text(encoding='utf-8'))
        if marker.get('purpose')!='isolated-barony-playtest' or marker.get('binary_sha256')!=binary.get('sha256') or marker.get('source_revision')!=baseline:
            raise ValueError('isolated launch marker identity mismatch')
        data_identity=record.get('data_manifest_sha256','')
        if len(data_identity)!=64 or marker.get('data_manifest_sha256')!=data_identity:
            raise ValueError('data manifest identity mismatch')
        data_entry=record.get('data_manifest', {})
        data_manifest=json.loads(checked_file(data_entry).read_text(encoding='utf-8'))
        if data_entry.get('sha256')!=data_identity or data_manifest.get('schema')!=1 or not data_manifest.get('files'):
            raise ValueError('missing data manifest subjects')
        files=data_manifest['files']; seen=set()
        if not isinstance(files,list): raise ValueError('manifest files must be a list')
        for entry in files:
            path=entry.get('path',''); parts=pathlib.PurePosixPath(path)
            if (not path or parts.is_absolute() or '..' in parts.parts or '\\' in path
                    or path in seen or entry.get('type')!='file'
                    or not isinstance(entry.get('size'),int) or entry['size']<0
                    or not re.fullmatch('[0-9a-f]{64}',entry.get('sha256',''))):
                raise ValueError('invalid data manifest file')
            seen.add(path)
        if marker.get('schema')!=1 or marker.get('target_os')!=record.get('platform') or marker.get('profile_id')!=record.get('isolated_profile'):
            raise ValueError('profile marker schema, platform or identity mismatch')
        for field in ('producer', 'recorded_at', 'platform', 'data_version', 'isolated_profile'):
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValueError('missing '+field)
        for name in ('build', 'launch', 'audio', 'save_isolation'):
            check=record.get('checks', {}).get(name, {})
            if check.get('status') != 'PASS':
                raise ValueError(name+' has not passed')
            relative=check.get('evidence_path', '')
            if not isinstance(relative, str) or not relative or pathlib.Path(relative).is_absolute():
                raise ValueError('invalid evidence path')
            log=(root/relative).resolve()
            log.relative_to(root.resolve())
            if not log.is_file() or log.stat().st_size == 0:
                raise ValueError('missing or empty evidence log')
            digest=hashlib.sha256(log.read_bytes()).hexdigest()
            if digest != check.get('sha256'):
                raise ValueError('evidence digest mismatch')
            observations=json.loads(log.read_text(encoding='utf-8'))
            if (observations.get('check')!=name or observations.get('status')!='PASS'
                    or observations.get('baseline_commit')!=baseline
                    or observations.get('binary_sha256')!=binary['sha256']
                    or observations.get('profile_marker_sha256')!=marker_entry['sha256']
                    or observations.get('data_manifest_sha256')!=data_identity
                    or observations.get('observer_id')!=observer['id']
                    or not isinstance(observations.get('observations'),list)
                    or not observations['observations']
                    or not all(isinstance(x,str) and x.strip() for x in observations['observations'])):
                raise ValueError('structured check is missing or bound to a different subject')
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise RuntimeError('Baseline gate blocked: '+str(exc)) from exc
    return record

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('action',choices=['restore','vanilla','stage-comfort']); args=ap.parse_args()
    if not shutil.which('git'): raise RuntimeError('Missing git')
    if args.action=='restore': restore('vanilla'); return
    if args.action=='stage-comfort':
        validate_baseline_evidence(ROOT/'evidence'/'baseline-passed.json')
        dest=restore('comfort')
        patch=str(ROOT/'patches'/'0001-comfort-diagnostics.patch')
        run('git','apply','--check',patch,cwd=dest); run('git','apply',patch,cwd=dest)
        print('Staged only; compile and runtime validation still required'); return
    missing=[x for x in ['cmake','c++'] if not shutil.which(x)]
    if missing: raise RuntimeError('Missing build tools: '+', '.join(missing))
    dest=restore('vanilla'); build=ROOT/'.work'/'build-vanilla'
    run('cmake','-S',str(dest),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release',
        '-DFMOD_ENABLED=OFF','-DOPENAL_ENABLED=OFF','-DSTEAMWORKS_ENABLED=0',
        '-DEOS_ENABLED=0','-DPLAYFAB_ENABLED=0')
    run('cmake','--build',str(build),'--parallel',str(min(4,os.cpu_count() or 1)))
    print('Compile completed. Runtime, assets, audio and four-player gates NOT passed.')
if __name__=='__main__':
    try: main()
    except (RuntimeError,subprocess.CalledProcessError) as exc:
        print(str(exc),file=sys.stderr); sys.exit(1)
