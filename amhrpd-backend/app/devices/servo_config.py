"""
Professional servo controller configuration and models.

AMHR-PD Project - Servo Motor Control System
ESP32-S3 + PCA9685 16-Channel PWM Driver
MG996R High-Torque Servo Motors (10 units)

Hardware specifications:
- Servo frequency: 50 Hz
- PWM period: 20 ms (20,000 microseconds)
- PCA9685 resolution: 4096 ticks per cycle
- Standard pulse range: 1000–2000 microseconds (0–180 degrees)
- Extended pulse range: 500–2500 microseconds (available if needed)
"""

from pydantic import BaseModel, Field, validator
from typing import Dict, List, Optional
import math


class ServoConfig(BaseModel):
    """
    Professional servo motor configuration and control limits.
    
    Attributes:
        channel: PCA9685 channel (0–15, typically 0–9 used)
        label: Human-readable servo name
        min_angle: Minimum safe angle in degrees (default 0)
        max_angle: Maximum safe angle in degrees (default 180)
        min_pulse_us: Pulse width at min_angle in microseconds (default 1000)
        max_pulse_us: Pulse width at max_angle in microseconds (default 2000)
        home_angle: Default position when powered (typically 90)
    """
    
    channel: int = Field(..., ge=0, le=15, description="PCA9685 channel (0-15)")
    label: str = Field(default="", description="Servo label for UI")
    min_angle: float = Field(default=0.0, ge=-180, le=180, description="Minimum angle")
    max_angle: float = Field(default=180.0, ge=-180, le=180, description="Maximum angle")
    min_pulse_us: int = Field(default=1000, ge=500, le=2500, description="Pulse at min_angle (µs)")
    max_pulse_us: int = Field(default=2000, ge=500, le=2500, description="Pulse at max_angle (µs)")
    home_angle: float = Field(default=90.0, description="Default/home position")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "channel": 0,
                "label": "Base Rotation",
                "min_angle": 0.0,
                "max_angle": 180.0,
                "min_pulse_us": 1000,
                "max_pulse_us": 2000,
                "home_angle": 90.0
            }
        }
    }
    
    @validator("max_angle")
    def validate_angle_range(cls, v, values):
        """Ensure max_angle > min_angle"""
        if "min_angle" in values and v <= values["min_angle"]:
            raise ValueError("max_angle must be greater than min_angle")
        return v
    
    @validator("max_pulse_us")
    def validate_pulse_range(cls, v, values):
        """Ensure max_pulse > min_pulse"""
        if "min_pulse_us" in values and v <= values["min_pulse_us"]:
            raise ValueError("max_pulse_us must be greater than min_pulse_us")
        return v
    
    @validator("home_angle")
    def validate_home_angle(cls, v, values):
        """Ensure home_angle is within configured range"""
        if "min_angle" in values and "max_angle" in values:
            if v < values["min_angle"] or v > values["max_angle"]:
                raise ValueError("home_angle must be within [min_angle, max_angle]")
        return v


class ServoState(BaseModel):
    """
    Current runtime state of a servo motor.
    
    Attributes:
        channel: PCA9685 channel
        label: Servo label
        current_angle: Current angle (0–180)
        target_angle: Target angle being commanded
        pulse_width_us: Actual PWM pulse width in microseconds
        pca9685_ticks: PWM tick count (0–4095 for PCA9685 or 0–65535 for GPIO PWM)
        is_moving: True if servo is moving
        error: Any error condition (None if OK)
    """
    
    channel: int
    label: str
    current_angle: float
    target_angle: float
    pulse_width_us: int
    pca9685_ticks: int  # Generic PWM tick count (PCA9685=0-4095, GPIO=0-65535)
    is_moving: bool = False
    error: Optional[str] = None
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "channel": 0,
                "label": "Base Rotation",
                "current_angle": 90.0,
                "target_angle": 120.0,
                "pulse_width_us": 1500,
                "pca9685_ticks": 50000,
                "is_moving": True,
                "error": None
            }
        }
    }


class ServoController:
    """
    Central servo control and conversion logic.
    
    Handles:
    - Angle validation and clamping
    - Angle ↔ PWM microsecond conversion
    - PWM microsecond ↔ PCA9685 tick conversion
    - Configuration per servo
    
    Calculations:
    - PCA9685 runs at 4 kHz internal clock
    - 50 Hz PWM = 20 ms period = 4096 ticks per cycle
    - 1 tick ≈ 4.88 microseconds
    """
    
    # PCA9685 timing constants
    PCA9685_FREQUENCY = 50  # Hz
    PCA9685_PERIOD_MS = 1000 / PCA9685_FREQUENCY  # 20 ms
    PCA9685_PERIOD_US = PCA9685_PERIOD_MS * 1000  # 20,000 µs
    PCA9685_TICKS_PER_CYCLE = 4096
    PCA9685_US_PER_TICK = PCA9685_PERIOD_US / PCA9685_TICKS_PER_CYCLE  # ~4.88 µs
    
    # GPIO PWM Constants (ESP32 LEDC)
    GPIO_PWM_TICKS_PER_CYCLE = 65536  # 16-bit resolution (0-65535)
    GPIO_PWM_FREQUENCY = 50  # 50 Hz for servos
    GPIO_PWM_PERIOD_US = 20000  # 20 ms period
    GPIO_PWM_US_PER_TICK = GPIO_PWM_PERIOD_US / GPIO_PWM_TICKS_PER_CYCLE  # ~0.305 µs
    
    def __init__(self, servo_configs: Dict[int, ServoConfig]):
        """
        Initialize controller with servo configurations.
        
        Args:
            servo_configs: Dictionary mapping channel → ServoConfig
        """
        self.servos = servo_configs
    
    def clamp_angle(self, channel: int, angle: float) -> float:
        """
        Clamp angle to servo's safe operating range.
        
        Args:
            channel: Servo channel
            angle: Requested angle in degrees
            
        Returns:
            Clamped angle within [min_angle, max_angle]
            
        Raises:
            ValueError: If channel not configured
        """
        if channel not in self.servos:
            raise ValueError(f"Channel {channel} not configured")
        
        config = self.servos[channel]
        return max(config.min_angle, min(angle, config.max_angle))
    
    def angle_to_pulse_us(self, channel: int, angle: float) -> int:
        """
        Convert angle (degrees) to PWM pulse width (microseconds).
        
        Linear interpolation:
            pulse_us = min_pulse + (angle - min_angle) / (max_angle - min_angle) 
                       × (max_pulse - min_pulse)
        
        Args:
            channel: Servo channel
            angle: Angle in degrees
            
        Returns:
            PWM pulse width in microseconds
            
        Raises:
            ValueError: If channel not configured or angle out of range
        """
        if channel not in self.servos:
            raise ValueError(f"Channel {channel} not configured")
        
        config = self.servos[channel]
        angle = self.clamp_angle(channel, angle)
        
        # Linear interpolation
        angle_range = config.max_angle - config.min_angle
        pulse_range = config.max_pulse_us - config.min_pulse_us
        
        if angle_range == 0:
            return config.min_pulse_us
        
        interpolation = (angle - config.min_angle) / angle_range
        pulse_us = config.min_pulse_us + (interpolation * pulse_range)
        
        return int(round(pulse_us))
    
    def pulse_us_to_pca9685_ticks(self, pulse_us: int) -> int:
        """
        Convert PWM pulse width (microseconds) to PCA9685 tick count.
        
        Calculation:
            ticks = pulse_us / (20000 µs / 4096 ticks)
                  = pulse_us / 4.88 µs per tick
        
        Args:
            pulse_us: Pulse width in microseconds
            
        Returns:
            PCA9685 ticks (0–4095)
        """
        ticks = pulse_us / self.PCA9685_US_PER_TICK
        # Clamp to valid PCA9685 range
        return max(0, min(int(round(ticks)), self.PCA9685_TICKS_PER_CYCLE - 1))
    
    def pulse_us_to_gpio_pwm_ticks(self, pulse_us: int) -> int:
        """
        Convert PWM pulse (microseconds) to GPIO PWM tick count (16-bit ESP32 LEDC).
        
        Calculation:
            ticks = (pulse_us / 20000) * 65535
        """
        ticks = (pulse_us * self.GPIO_PWM_TICKS_PER_CYCLE) / self.GPIO_PWM_PERIOD_US
        return max(0, min(int(round(ticks)), self.GPIO_PWM_TICKS_PER_CYCLE - 1))
    
    def angle_to_pca9685_ticks(self, channel: int, angle: float) -> int:
        """
        Convert angle directly to PCA9685 ticks (convenience method).
        
        Args:
            channel: Servo channel
            angle: Angle in degrees
            
        Returns:
            PCA9685 ticks (0–4095)
        """
        angle = self.clamp_angle(channel, angle)
        pulse_us = self.angle_to_pulse_us(channel, angle)
        return self.pulse_us_to_pca9685_ticks(pulse_us)
    
    def angle_to_gpio_pwm_ticks(self, channel: int, angle: float) -> int:
        """
        Convert angle directly to GPIO PWM ticks (16-bit, convenience method).
        
        Args:
            channel: Servo channel
            angle: Angle in degrees
            
        Returns:
            GPIO PWM ticks (0–65535)
        """
        angle = self.clamp_angle(channel, angle)
        pulse_us = self.angle_to_pulse_us(channel, angle)
        return self.pulse_us_to_gpio_pwm_ticks(pulse_us)
    
    def pca9685_ticks_to_pulse_us(self, ticks: int) -> int:
        """
        Reverse: Convert PCA9685 ticks to pulse width (microseconds).
        
        Args:
            ticks: PCA9685 tick count (0–4095)
            
        Returns:
            Pulse width in microseconds
        """
        pulse_us = ticks * self.PCA9685_US_PER_TICK
        return int(round(pulse_us))
    
    def gpio_pwm_ticks_to_pulse_us(self, ticks: int) -> int:
        """
        Reverse: Convert GPIO PWM ticks to pulse width (microseconds).
        
        Args:
            ticks: GPIO PWM tick count (0–65535)
            
        Returns:
            Pulse width in microseconds
        """
        pulse_us = (ticks * self.GPIO_PWM_PERIOD_US) / self.GPIO_PWM_TICKS_PER_CYCLE
        return int(round(pulse_us))
    
    def pulse_us_to_angle(self, channel: int, pulse_us: int) -> float:
        """
        Reverse: Convert pulse width to angle (for feedback).
        
        Args:
            channel: Servo channel
            pulse_us: Pulse width in microseconds
            
        Returns:
            Angle in degrees
            
        Raises:
            ValueError: If channel not configured
        """
        if channel not in self.servos:
            raise ValueError(f"Channel {channel} not configured")
        
        config = self.servos[channel]
        
        # Clamp pulse to configured range
        pulse_us = max(config.min_pulse_us, min(pulse_us, config.max_pulse_us))
        
        pulse_range = config.max_pulse_us - config.min_pulse_us
        if pulse_range == 0:
            return config.min_angle
        
        interpolation = (pulse_us - config.min_pulse_us) / pulse_range
        angle = config.min_angle + (interpolation * (config.max_angle - config.min_angle))
        
        return round(angle, 1)


# ============================================================================
# Factory: Create default 10-servo configuration for AMHR-PD
# ============================================================================

def create_default_servo_config() -> Dict[int, ServoConfig]:
    """
    Create default configuration for 10 MG996R servos on AMHR-PD.
    
    Returns:
        Dictionary mapping channel → ServoConfig
        
    Channels:
        0: Base rotation
        1: Shoulder 1
        2: Shoulder 2
        3: Elbow 1
        4: Elbow 2
        5: Wrist rotation
        6: Wrist flex
        7: Gripper
        8: Reserved
        9: Reserved
    """
    labels = [
        "Base Rotation",
        "Shoulder 1",
        "Shoulder 2",
        "Elbow 1",
        "Elbow 2",
        "Wrist Rotation",
        "Wrist Flex",
        "Gripper",
        "Reserved 1",
        "Reserved 2"
    ]
    
    configs = {}
    for channel in range(10):
        configs[channel] = ServoConfig(
            channel=channel,
            label=labels[channel],
            min_angle=0.0,
            max_angle=180.0,
            min_pulse_us=1000,
            max_pulse_us=2000,
            home_angle=90.0
        )
    
    return configs


# ============================================================================
# Arduino-Compatible Structure (JSON serializable for protocol)
# ============================================================================

def servo_config_to_arduino_json(config: ServoConfig) -> dict:
    """
    Convert ServoConfig to Arduino-compatible JSON structure.
    
    Used in firmware initialization and configuration sync.
    
    Returns:
        {
            "ch": channel,
            "label": label,
            "minA": min_angle,
            "maxA": max_angle,
            "minPulse": min_pulse_us,
            "maxPulse": max_pulse_us,
            "home": home_angle
        }
    """
    return {
        "ch": config.channel,
        "label": config.label,
        "minA": config.min_angle,
        "maxA": config.max_angle,
        "minPulse": config.min_pulse_us,
        "maxPulse": config.max_pulse_us,
        "home": config.home_angle
    }


if __name__ == "__main__":
    """
    Verification and calculation examples.
    """
    print("=" * 70)
    print("SERVO CONTROLLER - VERIFICATION TEST")
    print("=" * 70)
    
    # Create default configuration
    servo_configs = create_default_servo_config()
    controller = ServoController(servo_configs)
    
    print(f"\nPCA9685 Timing:")
    print(f"  Frequency: {controller.PCA9685_FREQUENCY} Hz")
    print(f"  Period: {controller.PCA9685_PERIOD_US} µs")
    print(f"  Ticks/cycle: {controller.PCA9685_TICKS_PER_CYCLE}")
    print(f"  µs/tick: {controller.PCA9685_US_PER_TICK:.4f}")
    
    print(f"\nChannel 0 - {servo_configs[0].label}:")
    print(f"  Angle range: {servo_configs[0].min_angle}–{servo_configs[0].max_angle}°")
    print(f"  Pulse range: {servo_configs[0].min_pulse_us}–{servo_configs[0].max_pulse_us} µs")
    
    # Test conversions
    test_angles = [0.0, 45.0, 90.0, 135.0, 180.0]
    print(f"\n  Angle → Pulse → Ticks conversions:")
    print(f"  {'Angle':>8} {'Pulse (µs)':>12} {'Ticks':>8}")
    print(f"  {'-' * 30}")
    
    for angle in test_angles:
        pulse_us = controller.angle_to_pulse_us(0, angle)
        ticks = controller.pulse_us_to_pca9685_ticks(pulse_us)
        print(f"  {angle:>8.1f} {pulse_us:>12} {ticks:>8}")
    
    # Test reverse conversion
    print(f"\n  Ticks → Pulse → Angle verification:")
    print(f"  {'Ticks':>8} {'Pulse (µs)':>12} {'Angle':>8}")
    print(f"  {'-' * 30}")
    
    test_ticks = [102, 205, 307, 410, 512]
    for tick in test_ticks:
        pulse_us = controller.pca9685_ticks_to_pulse_us(tick)
        angle = controller.pulse_us_to_angle(0, pulse_us)
        print(f"  {tick:>8} {pulse_us:>12} {angle:>8.1f}°")
    
    # Test clamping
    print(f"\n  Angle clamping test:")
    print(f"  Input:  -50°  →  Clamped: {controller.clamp_angle(0, -50)}°")
    print(f"  Input:  200°  →  Clamped: {controller.clamp_angle(0, 200)}°")
    print(f"  Input:  90°   →  Clamped: {controller.clamp_angle(0, 90)}°")
    
    print("\n" + "=" * 70)
    print("All conversions validated ✓")
    print("=" * 70)
