//! 咪咕 .mg3d：减法密码，对照 mg3d.py。

use std::fs;
use std::path::{Path, PathBuf};

const SEG: usize = 0x20;

fn is_upper_hex(ch: u8) -> bool {
    ch.is_ascii_digit() || (b'A'..=b'F').contains(&ch)
}

fn is_printable(ch: u8) -> bool {
    (0x20..=0x7E).contains(&ch)
}

fn sub(data: &[u8], key: &[u8]) -> Vec<u8> {
    data.iter()
        .enumerate()
        .map(|(i, b)| b.wrapping_sub(key[i % SEG]))
        .collect()
}

fn valid_header(h: &[u8]) -> bool {
    if h.len() < 0x18 || &h[..4] != b"RIFF" || &h[8..16] != b"WAVEfmt " {
        return false;
    }
    let fmt_size = u32::from_le_bytes(h[0x10..0x14].try_into().unwrap()) as usize;
    if !matches!(fmt_size, 16 | 18 | 40) {
        return false;
    }
    let off1 = 0x14 + fmt_size;
    if off1 + 8 > h.len() || !h[off1..off1 + 4].iter().all(|&c| is_printable(c)) {
        return false;
    }
    let chunk = u32::from_le_bytes(h[off1 + 4..off1 + 8].try_into().unwrap()) as usize;
    let off2 = off1 + 8 + chunk;
    if off2 + 4 <= h.len() && !h[off2..off2 + 4].iter().all(|&c| is_printable(c)) {
        return false;
    }
    true
}

/// 成功返回输出 wav 路径。
pub fn decrypt(path: &Path, outdir: &Path) -> Result<PathBuf, String> {
    let buf = fs::read(path).map_err(|e| e.to_string())?;
    let header_end = buf.len().min(0x100);
    let mut key = None;
    let mut off = SEG;
    while off < SEG * 20 {
        let end = off + SEG;
        if end > buf.len() {
            break;
        }
        let cand = &buf[off..end];
        if cand.iter().all(|&c| is_upper_hex(c)) {
            let header = sub(&buf[..header_end], cand);
            if valid_header(&header) {
                key = Some(cand.to_vec());
                break;
            }
        }
        off += SEG;
    }
    let key = key.ok_or_else(|| "未找到咪咕密钥（非 mg3d 格式？）".to_string())?;
    let data = sub(&buf, &key);
    fs::create_dir_all(outdir).map_err(|e| e.to_string())?;
    let stem = path.file_stem().unwrap_or_default().to_string_lossy();
    let out = outdir.join(format!("{stem}.wav"));
    fs::write(&out, data).map_err(|e| e.to_string())?;
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn tiny_wav() -> Vec<u8> {
        let data = vec![0u8; 160];
        let mut out = Vec::new();
        out.extend(b"RIFF");
        out.extend(&(36u32 + data.len() as u32).to_le_bytes());
        out.extend(b"WAVEfmt ");
        out.extend(&16u32.to_le_bytes());
        out.extend(&1u16.to_le_bytes());
        out.extend(&1u16.to_le_bytes());
        out.extend(&8000u32.to_le_bytes());
        out.extend(&16000u32.to_le_bytes());
        out.extend(&2u16.to_le_bytes());
        out.extend(&16u16.to_le_bytes());
        out.extend(b"data");
        out.extend(&(data.len() as u32).to_le_bytes());
        out.extend(data);
        out
    }

    #[test]
    fn synthetic_wav_roundtrip() {
        let wav = tiny_wav();
        assert_eq!(&wav[0x40..0x60], &[0u8; 32]);
        let key = b"0123456789ABCDEF0123456789ABCDEF";
        let enc: Vec<u8> = wav
            .iter()
            .enumerate()
            .map(|(i, b)| b.wrapping_add(key[i % 32]))
            .collect();
        let dir = tempdir().unwrap();
        let src = dir.path().join("song.mg3d");
        fs::write(&src, enc).unwrap();
        let out = decrypt(&src, dir.path()).unwrap();
        assert_eq!(fs::read(out).unwrap(), wav);
    }

    #[test]
    fn garbage_is_rejected() {
        let dir = tempdir().unwrap();
        let src = dir.path().join("nope.mg3d");
        fs::write(&src, b"not a mg3d file".repeat(20)).unwrap();
        let err = decrypt(&src, dir.path()).unwrap_err();
        assert!(err.contains("密钥"));
    }
}
