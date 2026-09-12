//! musicex 文件尾，对照 qmc_ekey.parse_musicex_footer。只读尾部，不吞整文件。

use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MusicexFooter {
    pub song_id: u32,
    pub media_mid: String,
    pub filename: String,
}

fn u16s(meta: &[u8], off: usize, maxlen: usize) -> String {
    let end = (off + maxlen).min(meta.len());
    if off >= end {
        return String::new();
    }
    let mut units = Vec::new();
    let mut i = off;
    while i + 1 < end {
        let c = u16::from_le_bytes([meta[i], meta[i + 1]]);
        if c == 0 {
            break;
        }
        units.push(c);
        i += 2;
    }
    String::from_utf16_lossy(&units)
}

pub fn parse_musicex_footer(path: &Path) -> Option<MusicexFooter> {
    let mut f = File::open(path).ok()?;
    let file_size = f.seek(SeekFrom::End(0)).ok()?;
    if file_size < 16 {
        return None;
    }
    f.seek(SeekFrom::End(-16)).ok()?;
    let mut tail = [0u8; 16];
    f.read_exact(&mut tail).ok()?;
    if &tail[8..] != b"musicex\x00" {
        return None;
    }
    let footer_size = u32::from_le_bytes(tail[0..4].try_into().ok()?);
    let version = u32::from_le_bytes(tail[4..8].try_into().ok()?);
    if version != 1 || footer_size <= 16 || footer_size as u64 > file_size.min(16 * 1024 * 1024) {
        return None;
    }
    f.seek(SeekFrom::End(-(footer_size as i64))).ok()?;
    let meta_len = footer_size as usize - 16;
    let mut meta = vec![0u8; meta_len];
    f.read_exact(&mut meta).ok()?;
    if meta.len() < 0x48 {
        return None;
    }
    Some(MusicexFooter {
        song_id: u32::from_le_bytes(meta[0..4].try_into().ok()?),
        media_mid: u16s(&meta, 0x0C, 60),
        filename: u16s(&meta, 0x48, 68),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[test]
    fn short_file_is_not_musicex() {
        let mut f = NamedTempFile::new().unwrap();
        f.write_all(b"short").unwrap();
        assert!(parse_musicex_footer(f.path()).is_none());
    }

    #[test]
    fn footer_is_parsed() {
        let mut metadata = vec![0u8; 0x90];
        metadata[0..4].copy_from_slice(&42u32.to_le_bytes());
        let mid: Vec<u8> = "media-mid".encode_utf16().flat_map(|c| c.to_le_bytes()).collect();
        metadata[0x0C..0x0C + mid.len()].copy_from_slice(&mid);
        let name: Vec<u8> = "track.mflac".encode_utf16().flat_map(|c| c.to_le_bytes()).collect();
        metadata[0x48..0x48 + name.len()].copy_from_slice(&name);
        let footer_size = (metadata.len() + 16) as u32;
        let mut f = NamedTempFile::new().unwrap();
        f.write_all(&metadata).unwrap();
        f.write_all(&footer_size.to_le_bytes()).unwrap();
        f.write_all(&1u32.to_le_bytes()).unwrap();
        f.write_all(b"musicex\0").unwrap();
        f.flush().unwrap();
        assert_eq!(
            parse_musicex_footer(f.path()).unwrap(),
            MusicexFooter {
                song_id: 42,
                media_mid: "media-mid".into(),
                filename: "track.mflac".into(),
            }
        );
    }
}
