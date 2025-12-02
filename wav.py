import wave
import time
import sys


def read_wav(wav_path):
    """
    读取 WAV 文件
    :param wav_path: 文件路径
    :return: (pcm_data, sample_rate, num_channels, is_ok)
    """
    try:
        with wave.open(wav_path, "rb") as wf:
            # 获取音频参数
            num_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()
            num_frames = wf.getnframes()

            # 读取所有数据
            pcm_data = wf.readframes(num_frames)

            # 简单的格式检查 (Unitree 通常需要 16-bit PCM)
            if sample_width != 2:
                print(f"[WAV] Warning: Sample width is {sample_width} bytes (expected 2 bytes/16-bit)")

            return pcm_data, sample_rate, num_channels, True

    except Exception as e:
        print(f"[WAV] Error reading file {wav_path}: {e}")
        return b"", 0, 0, False


def play_pcm_stream(client, pcm_data, name="default"):
    """
    分块播放 PCM 数据流
    :param client: AudioClient 实例
    :param pcm_data: 二进制音频数据 (bytes)
    :param name: 播放任务名称 (可选)
    """
    if not pcm_data:
        return

    # 分片大小 (字节)，取决于机器人的缓冲区大小
    # 通常 16k 采样率下，20ms-100ms 的数据块比较合适
    # 16000 Hz * 2 bytes * 0.1s = 3200 bytes
    CHUNK_SIZE = 3200

    total_len = len(pcm_data)
    offset = 0

    # 检查客户端是否有 VoicePlayer 方法 (Unitree SDK 常见接口)
    # 如果没有 VoicePlayer，尝试使用 TtsMaker 发送原始数据 (视具体SDK版本而定，通常 VoicePlayer 用于 PCM)
    use_voice_player = hasattr(client, 'VoicePlayer')

    if not use_voice_player:
        print("[WAV] Warning: 'VoicePlayer' method not found on AudioClient. Playback might fail.")
        return

    print(f"[WAV] Start playing stream ({total_len} bytes)...")

    while offset < total_len:
        # 获取当前分片
        end = min(offset + CHUNK_SIZE, total_len)
        chunk = pcm_data[offset:end]

        # 发送数据
        # 注意: 这里的 1004 是示例消息ID，SDK 内部可能会忽略或使用
        client.VoicePlayer(chunk, len(chunk))

        offset += CHUNK_SIZE

        # 稍微延时以防止发送过快溢出缓冲区
        # 发送 3200 字节 (约 0.1秒音频)，我们休眠稍微短一点的时间让缓冲区保持充盈
        time.sleep(0.08)

    print("[WAV] Playback finished sending.")