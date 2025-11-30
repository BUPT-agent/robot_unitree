import wave
import audioop
import os
import requests


def convert_to_16k_mono(src_path):
    """
    (内部工具) 将任意 WAV 转换为 16kHz、单声道、16bit
    """
    try:
        temp_path = src_path + ".converted.wav"

        with wave.open(src_path, 'rb') as s:
            params = s.getparams()
            n_channels = params.nchannels
            sampwidth = params.sampwidth
            framerate = params.framerate
            content = s.readframes(params.nframes)

        # 已经是完美格式，直接返回
        if n_channels == 1 and framerate == 16000 and sampwidth == 2:
            return src_path

        print(f"🔄 Auto-converting audio: {framerate}Hz/{n_channels}ch/{sampwidth * 8}bit -> 16k/Mono/16bit")

        # 1. 立体声转单声道
        if n_channels != 1:
            content = audioop.tomono(content, sampwidth, 0.5, 0.5)

        # 2. 重采样到 16000Hz
        if framerate != 16000:
            content, _ = audioop.ratecv(content, sampwidth, 1, framerate, 16000, None)

        # 3. 确保 16bit
        if sampwidth != 2:
            content = audioop.lin2lin(content, sampwidth, 2)

        with wave.open(temp_path, 'wb') as d:
            d.setnchannels(1)
            d.setsampwidth(2)
            d.setframerate(16000)
            d.writeframes(content)

        return temp_path

    except Exception as e:
        print(f"⚠️ Audio conversion warning: {e}")
        return src_path


def safe_upload_wav(session, base_url, filepath):
    """
    处理 WAV 文件的转换、上传和清理
    """
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return

    # 1. 转换格式
    upload_path = convert_to_16k_mono(filepath)
    is_converted = (upload_path != filepath)

    print(f"📤 Uploading WAV: {upload_path} ...")

    # 2. 执行上传
    try:
        url = f"{base_url.rstrip('/')}/cmd/play_wav"
        with open(upload_path, 'rb') as f:
            # 文件上传设置 10秒 超时
            resp = session.post(url, files={'file': f}, timeout=10)

        if resp.status_code == 200:
            print("✅ Upload success, robot is playing.")
        else:
            print(f"❌ Upload failed (Code: {resp.status_code}): {resp.text}")

    except Exception as e:
        print(f"❌ Error playing wav: {e}")

    finally:
        # 3. 清理临时文件
        if is_converted and os.path.exists(upload_path):
            try:
                os.remove(upload_path)
            except:
                pass