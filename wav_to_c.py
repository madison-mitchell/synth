#!/usr/bin/env python3
"""
Convert WAV files to C header files for embedding in Pico firmware.
Automatically resamples to 16kHz if needed using high-quality resampling.
"""

import sys
import os
import wave
import struct
import math
try:
    import scipy.signal
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

def _windowed_sinc(samples, target_rate, sourcerate):
    """
    High-quality resampling using windowed sinc interpolation.
    Significantly better than linear interpolation for downsampling.
    """
    import math
    
    # Use Kaiser window for good frequency response
    ratio = target_rate / sourcerate
    new_len = int(len(samples) * ratio)
    
    # Radius for sinc (higher = better quality but slower)
    radius = 11
    
    # Kaiser beta for transition width
    beta = 8.6
    
    # Create Kaiser window
    window_len = 2 * radius + 1
    window = []
    for i in range(window_len):
        x = (i - radius) / radius
        # Approximate Kaiser window
        ix0 = beta * math.sqrt(max(0, 1 - x*x))
        # Approximate Bessel I0
        sum_val = 1 + (ix0/2)**2
        for n in range(2, 20):
            sum_val += ((ix0/2)**n / math.factorial(n))**2
        window.append(sum_val**0.5)
    
    # Normalize window
    window_sum = sum(window)
    window = [w / window_sum for w in window]
    
    resampled = []
    for i in range(new_len):
        pos = i / ratio
        idx = int(pos)
        frac = pos - idx
        
        # Sinc interpolation using windowed kernel
        val = 0.0
        for k in range(-radius, radius + 1):
            sample_idx = idx + k
            if 0 <= sample_idx < len(samples):
                # Sinc function
                x = (k - frac) * math.pi
                if abs(x) < 0.01:
                    sinc_val = 1.0
                else:
                    sinc_val = math.sin(x) / x
                    
                window_idx = k + radius
                val += samples[sample_idx] * sinc_val * window[window_idx]
        
        resampled.append(int(max(-32768, min(32767, val))))
    
    return resampled

def _linear_resample(samples, new_len):
    """Simple linear interpolation resampling."""
    resampled = []
    ratio = len(samples) / new_len
    for i in range(new_len):
        old_i = i * ratio
        idx = int(old_i)
        frac = old_i - idx
        
        if idx + 1 < len(samples):
            s = samples[idx] * (1 - frac) + samples[idx + 1] * frac
        else:
            s = samples[idx]
        resampled.append(int(max(-32768, min(32767, s))))
    return resampled

def wav_to_c(wav_file, symbol_name, output_header):
    """Convert a WAV file to a C header with embedded audio data."""
    
    try:
        with wave.open(wav_file, 'rb') as wav:
            n_channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            framerate = wav.getframerate()
            n_frames = wav.getnframes()
            
            print(f"  {os.path.basename(wav_file)}: {n_channels}ch, {framerate}Hz, {n_frames} frames, {sample_width} bytes/sample")
            
            # Read all audio frames
            frames = wav.readframes(n_frames)
            
            # Convert to int16 samples (mono)
            samples = []
            for i in range(n_frames):
                offset = i * sample_width * n_channels
                
                # Extract left channel (or mono)
                if sample_width == 1:
                    sample = struct.unpack('B', frames[offset:offset+1])[0] - 128
                    sample = sample * 256  # convert to 16-bit
                elif sample_width == 2:
                    sample = struct.unpack('<h', frames[offset:offset+2])[0]
                elif sample_width == 3:
                    b = frames[offset:offset+3]
                    sample = struct.unpack('<I', b + b'\x00')[0]
                    if sample & 0x800000:
                        sample = sample - 0x1000000
                    sample = sample >> 8
                else:
                    sample = struct.unpack('<i', frames[offset:offset+4])[0] >> 16
                
                samples.append(int(sample))
            
            # Resample to 16kHz if necessary
            target_rate = 16000
            if framerate != target_rate:
                ratio = target_rate / framerate
                
                if HAS_SCIPY:
                    # Use scipy's high-quality polyphase resampler
                    try:
                        resampled = scipy.signal.resample_poly(samples, target_rate, framerate)
                        resampled = [int(max(-32768, min(32767, s))) for s in resampled]
                        print(f"    Resampled to {target_rate}Hz (scipy): {len(resampled)} samples")
                    except Exception as e:
                        print(f"    Scipy resample failed: {e}, using windowed-sinc")
                        resampled = _windowed_sinc(samples, target_rate, framerate)
                        print(f"    Resampled to {target_rate}Hz (windowed-sinc): {len(resampled)} samples")
                else:
                    # Use high-quality windowed-sinc interpolation
                    resampled = _windowed_sinc(samples, target_rate, framerate)
                    print(f"    Resampled to {target_rate}Hz (windowed-sinc): {len(resampled)} samples")
                
                samples = resampled
            else:
                print(f"    Using original 16kHz: {len(samples)} samples")
            
            # Clamp all samples to 16-bit range
            samples = [max(-32768, min(32767, s)) for s in samples]
            
            # Write C header
            with open(output_header, 'w') as f:
                f.write(f"// Auto-generated from {os.path.basename(wav_file)}\n")
                f.write(f"// Sample rate: {target_rate} Hz, Samples: {len(samples)}\n\n")
                f.write(f"#ifndef __{symbol_name.upper()}_H__\n")
                f.write(f"#define __{symbol_name.upper()}_H__\n\n")
                f.write(f"#include <stdint.h>\n\n")
                f.write(f"const int {symbol_name}_len = {len(samples)};\n")
                f.write(f"const int16_t {symbol_name}_data[] = {{\n")
                
                # Write samples in chunks of 16 per line
                for i in range(0, len(samples), 16):
                    chunk = samples[i:i+16]
                    line = "    " + ", ".join(f"{s:6d}" for s in chunk)
                    if i + 16 < len(samples):
                        line += ","
                    f.write(line + "\n")
                
                f.write("};\n\n")
                f.write(f"#endif // __{symbol_name.upper()}_H__\n")
            
            print(f"  -> {output_header}")
            return len(samples)
    
    except Exception as e:
        print(f"ERROR processing {wav_file}: {e}", file=sys.stderr)
        return 0

def main():
    audio_dir = os.path.join(os.path.dirname(__file__), "audio")
    output_dir = os.path.dirname(__file__)
    
    # Define mapping: 4 drum pads to specific WAV files
    # These are the 4 keys in row 0 (keys 0-3 in key_assign)
    drum_mappings = [
        ("Rock-Kit-Kick-ff-1.wav", "drum_kick"),
        ("Rock-Snare-ff-1.wav", "drum_snare"),
        ("Rock-Kit-HiHat-Tip-1.wav", "drum_hihat"),
        ("Rock-Kit-Floor-1.wav", "drum_floor"),
    ]
    
    print("Converting drum samples to C headers...")
    
    total_samples = 0
    for wav_file, symbol in drum_mappings:
        wav_path = os.path.join(audio_dir, wav_file)
        if not os.path.exists(wav_path):
            print(f"WARNING: {wav_file} not found, skipping")
            continue
        
        header_path = os.path.join(output_dir, f"{symbol}.h")
        samples = wav_to_c(wav_path, symbol, header_path)
        total_samples += samples
    
    # Create a master header that includes all drums
    master_header = os.path.join(output_dir, "drum_samples.h")
    with open(master_header, 'w') as f:
        f.write("// Master header for drum samples\n")
        f.write("// Auto-generated by wav_to_c.py\n\n")
        f.write("#ifndef __DRUM_SAMPLES_H__\n")
        f.write("#define __DRUM_SAMPLES_H__\n\n")
        f.write("#include <stdint.h>\n")
        f.write("#include \"drum_kick.h\"\n")
        f.write("#include \"drum_snare.h\"\n")
        f.write("#include \"drum_hihat.h\"\n")
        f.write("#include \"drum_floor.h\"\n\n")
        f.write("// Array of drum samples for easy access\n")
        f.write("typedef struct {\n")
        f.write("    const int16_t *data;\n")
        f.write("    int len;\n")
        f.write("    const char *name;\n")
        f.write("} DrumSample;\n\n")
        f.write("static const DrumSample drum_samples[4] = {\n")
        f.write("    {drum_kick_data, drum_kick_len, \"kick\"},\n")
        f.write("    {drum_snare_data, drum_snare_len, \"snare\"},\n")
        f.write("    {drum_hihat_data, drum_hihat_len, \"hihat\"},\n")
        f.write("    {drum_floor_data, drum_floor_len, \"floor\"},\n")
        f.write("};\n\n")
        f.write("#endif // __DRUM_SAMPLES_H__\n")
    
    print(f"\n✓ Created {master_header}")
    print(f"✓ Total samples: {total_samples}")

if __name__ == "__main__":
    main()
