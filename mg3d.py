#!/usr/bin/env python3
"""咪咕音乐 .mg3d 解密（算法移植自 ioococ/music-unlock 的 mg3d.ts）。
原理：减法密码——文件中藏着一段 0x20 字节的大写十六进制字符串作密钥，
密文逐字节减去密钥循环。用 RIFF/WAVE 头结构反推验证密钥，无需外部凭据。"""
import os

SEG = 0x20


def _is_upper_hex(ch):
    return (0x30 <= ch <= 0x39) or (0x41 <= ch <= 0x46)


def _is_printable(ch):
    return 0x20 <= ch <= 0x7E


def _sub(data, key):
    return bytes(b - key[i % SEG] & 0xFF for i, b in enumerate(data))


def _valid_header(h):
    if h[:4] != b"RIFF" or h[8:16] != b"WAVEfmt ":
        return False
    fmt_size = int.from_bytes(h[0x10:0x14], "little")
    if fmt_size not in (16, 18, 40):
        return False
    off1 = 0x14 + fmt_size
    if not all(_is_printable(c) for c in h[off1:off1 + 4]):
        return False
    off2 = off1 + 8 + int.from_bytes(h[off1 + 4:off1 + 8], "little")
    if off2 <= len(h) and not all(_is_printable(c) for c in h[off2:off2 + 4]):
        return False
    return True


def mg3d_decrypt(path, outdir):
    """返回 (成功与否, 输出路径或失败原因)。"""
    with open(path, "rb") as f:
        buf = f.read()
    header = buf[:0x100]
    key = None
    for off in range(SEG, SEG * 20, SEG):
        cand = buf[off:off + SEG]
        if len(cand) < SEG or not all(_is_upper_hex(c) for c in cand):
            continue
        if _valid_header(_sub(header, cand)):
            key = cand
            break
    if key is None:
        return False, "未找到咪咕密钥（非 mg3d 格式？）"
    data = _sub(buf, key)
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, os.path.splitext(os.path.basename(path))[0] + ".wav")
    with open(out, "wb") as f:
        f.write(data)
    return True, out
