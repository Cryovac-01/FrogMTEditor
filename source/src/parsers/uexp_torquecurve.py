"""
Torque Curve .uexp parser for Motor Town CurveFloat files.
Handles FRichCurve with 3 or 5 key points.

Binary format:
  [4-byte header] [int32 num_keys] [key records] [8-byte footer]

Key record (27 bytes each):
  [InterpMode:u8] [TangentMode:u8] [TangentWeightMode:u8]
  [Time:f32] [Value:f32]
  [ArriveTangent:f32] [ArriveTangentWeight:f32]
  [LeaveTangent:f32] [LeaveTangentWeight:f32]
"""
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Any, Tuple


FOOTER = b'\x00\x00\x00\x00\xc1\x83\x2a\x9e'
KEY_SIZE = 27  # 3 bytes + 6 floats


@dataclass
class CurveKey:
    """Single key point on a torque curve."""
    interp_mode: int        # 0=Linear, 1=Constant, 2=Cubic
    tangent_mode: int       # 0=Auto, 1=User, 2=Break
    tangent_weight_mode: int
    time: float             # 0.0 to 1.0+ (fraction of MaxRPM)
    value: float            # 0.0 to 1.0 (torque multiplier)
    arrive_tangent: float
    arrive_tangent_weight: float
    leave_tangent: float
    leave_tangent_weight: float


@dataclass
class TorqueCurveData:
    """Parsed torque curve data."""
    header_bytes: bytes     # 4 bytes
    keys: List[CurveKey]
    raw_bytes: bytes

    @property
    def num_keys(self) -> int:
        return len(self.keys)

    def get_points(self) -> List[Tuple[float, float]]:
        """Get (time, value) pairs for visualization."""
        return [(k.time, k.value) for k in self.keys]

    def evaluate(self, t: float) -> float:
        """Evaluate curve at normalized RPM position t (0-1).
        Uses linear interpolation between key points."""
        if not self.keys:
            return 1.0
        if t <= self.keys[0].time:
            return self.keys[0].value
        if t >= self.keys[-1].time:
            return self.keys[-1].value

        # Find surrounding keys
        for i in range(len(self.keys) - 1):
            k0 = self.keys[i]
            k1 = self.keys[i + 1]
            if k0.time <= t <= k1.time:
                # Linear interpolation (simplified; real UE uses Hermite)
                if k1.time == k0.time:
                    return k0.value
                alpha = (t - k0.time) / (k1.time - k0.time)
                return k0.value + alpha * (k1.value - k0.value)

        return self.keys[-1].value

    def find_peak_power_factor(self, num_samples: int = 1000) -> float:
        """Find the curve factor at peak power RPM.
        Returns max(value * t) over the curve, divided by the t where it occurs.
        This gives the effective 'curve_factor' for HP calculation."""
        best_power = 0.0
        best_t = 0.5
        for i in range(1, num_samples + 1):
            t = i / num_samples
            v = self.evaluate(t)
            power = v * t  # Proportional to torque * RPM
            if power > best_power:
                best_power = power
                best_t = t
        if best_t > 0:
            return best_power / best_t  # = value at peak power RPM
        return 1.0

    def to_display_dict(self) -> Dict[str, Any]:
        result = {
            'NumKeys': {'raw': self.num_keys, 'display': str(self.num_keys), 'unit': 'points'},
        }
        for i, key in enumerate(self.keys):
            result[f'Key_{i}_Time'] = {'raw': key.time, 'display': f"{key.time:.3f}", 'unit': ''}
            result[f'Key_{i}_Value'] = {'raw': key.value, 'display': f"{key.value:.3f}", 'unit': ''}
            result[f'Key_{i}_InterpMode'] = {'raw': key.interp_mode,
                                              'display': ['Linear', 'Constant', 'Cubic'][key.interp_mode]
                                              if key.interp_mode < 3 else str(key.interp_mode),
                                              'unit': ''}
        return result


def parse_torque_curve(data: bytes) -> TorqueCurveData:
    """Parse a torque curve .uexp file."""
    header = data[:4]
    num_keys = struct.unpack_from('<i', data, 4)[0]

    keys = []
    offset = 8
    for _ in range(num_keys):
        interp = data[offset]
        tangent = data[offset + 1]
        weight_mode = data[offset + 2]
        time = struct.unpack_from('<f', data, offset + 3)[0]
        value = struct.unpack_from('<f', data, offset + 7)[0]
        arrive_t = struct.unpack_from('<f', data, offset + 11)[0]
        arrive_w = struct.unpack_from('<f', data, offset + 15)[0]
        leave_t = struct.unpack_from('<f', data, offset + 19)[0]
        leave_w = struct.unpack_from('<f', data, offset + 23)[0]

        keys.append(CurveKey(
            interp_mode=interp,
            tangent_mode=tangent,
            tangent_weight_mode=weight_mode,
            time=time, value=value,
            arrive_tangent=arrive_t, arrive_tangent_weight=arrive_w,
            leave_tangent=leave_t, leave_tangent_weight=leave_w,
        ))
        offset += KEY_SIZE

    return TorqueCurveData(header_bytes=header, keys=keys, raw_bytes=data)


def serialize_torque_curve(curve: TorqueCurveData) -> bytes:
    """Serialize torque curve back to binary."""
    parts = [curve.header_bytes]
    parts.append(struct.pack('<i', len(curve.keys)))

    for key in curve.keys:
        parts.append(bytes([key.interp_mode, key.tangent_mode, key.tangent_weight_mode]))
        parts.append(struct.pack('<f', key.time))
        parts.append(struct.pack('<f', key.value))
        parts.append(struct.pack('<f', key.arrive_tangent))
        parts.append(struct.pack('<f', key.arrive_tangent_weight))
        parts.append(struct.pack('<f', key.leave_tangent))
        parts.append(struct.pack('<f', key.leave_tangent_weight))

    parts.append(FOOTER)
    return b''.join(parts)


def shift_peak_torque(curve: TorqueCurveData, target_t: float) -> None:
    """Shift the peak torque point to a new normalized RPM position.

    Moves the key where value is closest to 1.0 to ``target_t`` and scales
    all intermediate key times proportionally so the curve shape is preserved.
    The endpoints (t=0 idle and t>=1.0 redline/overrev) are left untouched.

    Args:
        curve: Parsed torque curve to modify **in place**.
        target_t: Desired normalized RPM for peak torque (0.0–1.0).
                  For example 0.35 means peak at 35 % of MaxRPM.
    """
    if not curve.keys or target_t <= 0:
        return

    # Find the current peak key (highest value, excluding endpoints)
    peak_idx = None
    peak_val = -1.0
    for i, k in enumerate(curve.keys):
        if k.value > peak_val:
            peak_val = k.value
            peak_idx = i

    if peak_idx is None or peak_idx == 0:
        return

    old_peak_t = curve.keys[peak_idx].time
    if old_peak_t <= 0:
        return

    # Scale ratio for keys between idle and peak
    ratio = target_t / old_peak_t

    for i, k in enumerate(curve.keys):
        if i == 0:
            continue  # leave idle point
        if k.time >= 1.0:
            continue  # leave redline and overrev points
        if i == peak_idx:
            k.time = target_t
        elif k.time < old_peak_t:
            # Pre-peak: scale proportionally
            k.time = k.time * ratio
        else:
            # Post-peak, pre-redline: interpolate between new peak and 1.0
            if old_peak_t < 1.0:
                frac = (k.time - old_peak_t) / (1.0 - old_peak_t)
                k.time = target_t + frac * (1.0 - target_t)


def set_peak_hp_rpm(curve: TorqueCurveData, hp_t: float, torque_t: float) -> None:
    """Adjust the post-peak falloff so peak power occurs at ``hp_t``.

    Finds the curve segment that contains ``hp_t`` and adjusts the segment's
    end-key value so that ``curve(t) * t`` is maximised at ``hp_t``.

    General formula for a segment from (t_b, v_b) to (t_a, v_a):
        v_a = v_b * (2 * t_hp - t_a) / (2 * t_hp - t_b)

    Works with any curve shape — standard 5-point, diesel, electric, etc.

    Args:
        curve: Parsed torque curve to modify **in place** (peak should
               already be positioned at ``torque_t``).
        hp_t:  Normalised RPM for peak HP (0.0–1.0).
        torque_t: Normalised RPM where peak torque sits (0.0–1.0).
    """
    if not curve.keys or hp_t <= torque_t:
        return

    # Sort keys by time to find the right segment
    sorted_keys = sorted(curve.keys, key=lambda k: k.time)

    # Find the segment that contains hp_t: the key before and key after
    key_before = None
    key_after = None
    for i in range(len(sorted_keys) - 1):
        k0 = sorted_keys[i]
        k1 = sorted_keys[i + 1]
        if k0.time <= hp_t <= k1.time:
            key_before = k0
            key_after = k1
            break

    # If hp_t is beyond all keys (e.g. at redline with no key there),
    # use the last two keys that bracket or are closest
    if key_before is None:
        # hp_t might be past the last pre-overrev key — find the last
        # segment before hp_t
        for i in range(len(sorted_keys) - 1, 0, -1):
            if sorted_keys[i - 1].time <= hp_t:
                key_before = sorted_keys[i - 1]
                key_after = sorted_keys[i]
                break

    if key_before is None or key_after is None:
        return

    t_b = key_before.time
    v_b = key_before.value
    t_a = key_after.time

    denom = 2.0 * hp_t - t_b
    if denom <= 0:
        return

    new_v_a = v_b * (2.0 * hp_t - t_a) / denom
    new_v_a = max(0.10, min(0.95, new_v_a))

    # Apply to the actual key object in curve.keys (not the sorted copy)
    for k in curve.keys:
        if k is key_after:
            k.value = new_v_a
            return


def set_target_hp_curve(curve: TorqueCurveData, hp_t: float,
                        target_curve_val: float) -> None:
    """Scale post-peak falloff so the curve produces a specific HP value.

    Uses physics: ``HP = MaxTorque_Nm × curve(t) × RPM / 7121``, so the
    caller pre-computes ``target_curve_val = desired_HP × 7121 /
    (MaxTorque_Nm × peak_hp_rpm)`` and this function scales the entire
    post-peak region of the curve so the interpolated value at ``hp_t``
    equals that target.

    The scaling preserves the *shape* of the falloff while shifting its
    magnitude.  Each post-peak key's "drop from 1.0" is scaled by the
    ratio ``(1 - target) / (1 - original_at_hp_t)`` so that the curve
    naturally evaluates to ``target_curve_val`` at ``hp_t``.

    Args:
        curve: Parsed torque curve to modify **in place**.
        hp_t: Normalised RPM for peak HP (0.0–1.0).
        target_curve_val: Required curve multiplier at hp_t (typically < 1.0).
    """
    if not curve.keys or target_curve_val <= 0:
        return

    target_curve_val = max(0.05, min(1.0, target_curve_val))

    # Find the peak key (highest value)
    peak_val = max(k.value for k in curve.keys)
    if peak_val <= 0:
        return

    # Evaluate the curve at hp_t BEFORE adjustment to get the original value
    original_at_hp = curve.evaluate(hp_t)

    # Compute scale factor for the "drop from peak"
    # Original drop: peak_val - original_at_hp
    # Target drop:   peak_val - target_curve_val
    original_drop = peak_val - original_at_hp
    target_drop = peak_val - target_curve_val

    if original_drop <= 0.001:
        # Curve is flat after peak — can't scale the drop, so set all
        # post-peak keys to target_curve_val directly
        sorted_keys = sorted(curve.keys, key=lambda k: k.time)
        peak_t = max(k.time for k in curve.keys if k.value >= peak_val - 0.001)
        for k in curve.keys:
            if k.time > peak_t:
                k.value = max(0.05, target_curve_val)
        return

    drop_scale = target_drop / original_drop

    # Find peak time to know which keys are post-peak
    sorted_keys = sorted(curve.keys, key=lambda k: k.time)
    peak_t = 0.0
    for k in sorted_keys:
        if k.value >= peak_val - 0.001:
            peak_t = k.time

    # Scale all post-peak keys
    for k in curve.keys:
        if k.time > peak_t:
            old_drop = peak_val - k.value
            new_val = peak_val - old_drop * drop_scale
            k.value = max(0.05, min(1.0, new_val))


def build_shifted_curve(template_data: bytes, peak_torque_rpm: float,
                        max_rpm: float,
                        peak_hp_rpm: float = 0.0,
                        max_hp: float = 0.0,
                        max_torque_nm: float = 0.0) -> bytes:
    """Parse a torque curve, reshape it to match target RPM values, and
    re-serialize.

    Args:
        template_data: Raw .uexp bytes of the template torque curve.
        peak_torque_rpm: Desired peak torque RPM (e.g. 3500).
        max_rpm: Engine's MaxRPM (e.g. 7000).
        peak_hp_rpm: Desired peak HP RPM.  Must be > peak_torque_rpm.
        max_hp: Desired peak HP value (e.g. 601).  When provided with
                max_torque_nm, the curve falloff is shaped so that
                Power = MaxTorque × curve(hp_t) × peak_hp_rpm / 9549
                equals max_hp.
        max_torque_nm: MaxTorque in Nm (e.g. 2850).  Required when max_hp
                       is provided.

    Returns:
        New .uexp bytes with shifted curve (same size as original).
    """
    curve = parse_torque_curve(template_data)
    torque_t = peak_torque_rpm / max_rpm if max_rpm > 0 else 0.5
    torque_t = max(0.05, min(0.95, torque_t))
    shift_peak_torque(curve, torque_t)

    if peak_hp_rpm > peak_torque_rpm and max_rpm > 0:
        hp_t = peak_hp_rpm / max_rpm
        hp_t = max(torque_t + 0.02, min(1.0, hp_t))

        if max_hp > 0 and max_torque_nm > 0 and peak_hp_rpm > 0:
            # Compute the curve multiplier at hp_t so the engine produces
            # the desired HP at peak_hp_rpm.
            # HP = MaxTorque_Nm × curve(t) × RPM / 7121
            # Solve: curve(hp_t) = max_hp × 7121 / (MaxTorque × peak_hp_rpm)
            target_curve_val = max_hp * 7121.0 / (max_torque_nm * peak_hp_rpm)
            set_target_hp_curve(curve, hp_t, target_curve_val)
        else:
            # Fallback: geometric positioning only (no HP target)
            set_peak_hp_rpm(curve, hp_t, torque_t)

    return serialize_torque_curve(curve)


def round_trip_test(data: bytes) -> bool:
    try:
        curve = parse_torque_curve(data)
        rebuilt = serialize_torque_curve(curve)
        return rebuilt == data
    except Exception:
        return False
