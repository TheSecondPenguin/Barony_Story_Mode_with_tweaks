#include "adventurer_comfort.hpp"

using AdventurerComfort::useCameraBobbing;
using AdventurerComfort::useMouseSmoothing;
using AdventurerComfort::useSideSway;

static_assert(
    AdventurerComfort::isControllerMouseEvent(
        AdventurerComfort::controllerMouseEventWindowId),
    "tagged synthetic motion is recognized");
static_assert(
    !AdventurerComfort::isControllerMouseEvent(1),
    "a physical window event is not controller motion");
static_assert(
    AdventurerComfort::shouldMarkMouseCameraInput(0, 0, 1),
    "physical mouse updates its keyboard-owned camera state");
static_assert(
    !AdventurerComfort::shouldMarkMouseCameraInput(
        0, 0, AdventurerComfort::controllerMouseEventWindowId),
    "synthetic controller motion does not become mouse input");
static_assert(
    !AdventurerComfort::shouldMarkMouseCameraInput(1, 0, 1),
    "physical mouse cannot change another local player's camera state");

// Default-off Adventurer controls must be an identity transformation.
static_assert(!useMouseSmoothing(false, false, false, false), "disabled smoothing stays disabled");
static_assert(useMouseSmoothing(true, false, false, false), "mouse smoothing default is preserved");
static_assert(useMouseSmoothing(true, false, true, true), "controller smoothing default is preserved");
static_assert(!useCameraBobbing(false, false), "disabled bobbing stays disabled");
static_assert(useCameraBobbing(true, false), "bobbing default is preserved");
static_assert(useSideSway(false, false), "side sway default is preserved");

// Raw mouse follows the active input marker, so an idle connected controller
// does not suppress the requested mouse path and active controller input keeps
// its configured smoothing behavior.
static_assert(!useMouseSmoothing(true, true, false, false), "raw mouse bypasses smoothing");
static_assert(!useMouseSmoothing(true, true, false, true), "stale marker cannot invent a controller");
static_assert(!useMouseSmoothing(true, true, true, false), "idle connected controller permits raw mouse");
static_assert(useMouseSmoothing(true, true, true, true), "active controller keeps smoothing");
static_assert(!useMouseSmoothing(false, true, true, true), "raw mouse does not enable smoothing");

// No-bob resets vertical bob and its coupled side sway. The narrower switch
// can suppress side sway while retaining vertical bob.
static_assert(!useCameraBobbing(true, true), "no-bob suppresses configured bobbing");
static_assert(!useSideSway(true, false), "no-bob also suppresses side sway");
static_assert(!useSideSway(false, true), "side-sway switch suppresses sway");

int main()
{
	return 0;
}
