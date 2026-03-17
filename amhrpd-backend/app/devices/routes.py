from fastapi import APIRouter, Request, HTTPException

router = APIRouter(prefix="/servo", tags=["servo"])


def _default_servo_states() -> dict:
    # Dashboard expects a dict keyed by channel.
    # Until the ESP sends status/feedback, return a safe default.
    states = {}
    for ch in range(10):
        states[ch] = {
            "channel": ch,
            "current_angle": 0.0,
            "target_angle": 0.0,
            "is_moving": False,
        }
    return states


@router.get("/all")
async def all_servos():
    return _default_servo_states()


async def send_pose(request: Request, pose: str):
    if not hasattr(request.app.state, "command_router"):
        raise HTTPException(500, "Command router not initialized")

    router_obj = request.app.state.command_router

    command = await router_obj.route_command(
        device_type="esp32s3",
        command_name=pose,
        payload={}
    )

    return {
        "pose": pose,
        "command_id": command.command_id,
        "status": command.status
    }


@router.post("/pose/reset")
async def reset_pose(request: Request):
    return await send_pose(request, "resetposition")


@router.post("/pose/handsup")
async def handsup_pose(request: Request):
    return await send_pose(request, "handsup")


@router.post("/pose/headup")
async def headup_pose(request: Request):
    return await send_pose(request, "headup")


@router.post("/pose/headleft")
async def headleft_pose(request: Request):
    return await send_pose(request, "headleft")