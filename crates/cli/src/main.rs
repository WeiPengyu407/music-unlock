//! 最小 CLI：.mg3d 走 core，QMC 走已有 Rust 库，其余交给 um。

use music_unlock_core::{
    default_roots, find_db, mg3d_decrypt, parse_musicex_footer, KggPaths, OUT_NAME,
};
use qmc_decoder::{decrypt_file, determine_output_path, Format};
use std::env;
use std::path::{Path, PathBuf};
use std::process::{exit, Command};

fn main() {
    let mut outdir = None;
    let mut files = Vec::new();
    let mut args = env::args().skip(1);
    while let Some(a) = args.next() {
        if a == "-o" || a == "--output" {
            outdir = args.next();
        } else if a == "-h" || a == "--help" {
            eprintln!("用法: music-unlock [-o 输出目录] 文件...");
            exit(0);
        } else {
            files.push(a);
        }
    }
    if files.is_empty() {
        eprintln!("用法: music-unlock [-o 输出目录] 文件...");
        exit(2);
    }
    let mut failed = 0;
    for f in files {
        let path = PathBuf::from(&f);
        let dest = match &outdir {
            Some(d) => PathBuf::from(d),
            None => path
                .parent()
                .unwrap_or_else(|| Path::new("."))
                .join(OUT_NAME),
        };
        match unlock(&path, &dest) {
            Ok(out) => println!("{} -> {}", path.display(), out.display()),
            Err(e) => {
                eprintln!("{}: {e}", path.display());
                failed += 1;
            }
        }
    }
    if failed > 0 {
        exit(1);
    }
}

fn unlock(path: &Path, outdir: &Path) -> Result<PathBuf, String> {
    let ext = path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    if ext == "mg3d" {
        return mg3d_decrypt(path, outdir);
    }
    if ext == "kgg" {
        let db = find_db(&KggPaths {
            mu_dir: mu_dir(),
            roots: default_roots(),
        })
        .ok_or("需要酷狗登录态（找不到 KGMusicV3.db）")?;
        return um(path, outdir, Some(&db));
    }
    if let Some(fmt) = Format::from_extension(&ext) {
        if let Some(info) = parse_musicex_footer(path) {
            return Err(format!(
                "musicex 需要 ekey（song_id={} mid={}）。CLI 第一刀还没接 QQ 登录态",
                info.song_id, info.media_mid
            ));
        }
        std::fs::create_dir_all(outdir).map_err(|e| e.to_string())?;
        let output = determine_output_path(path, Some(outdir), fmt);
        decrypt_file(path, &output, fmt, None)?;
        return Ok(output);
    }
    um(path, outdir, None)
}

fn um(path: &Path, outdir: &Path, kgg_db: Option<&Path>) -> Result<PathBuf, String> {
    let exe = find_um().ok_or("找不到 um，本地 ncm/kgg 等格式需要它")?;
    std::fs::create_dir_all(outdir).map_err(|e| e.to_string())?;
    let mut cmd = Command::new(&exe);
    cmd.args(["-i", &path.to_string_lossy(), "-o", &outdir.to_string_lossy(), "--overwrite"]);
    if let Some(db) = kgg_db {
        cmd.args(["--kgg-db", &db.to_string_lossy()]);
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000);
    }
    let out = cmd.output().map_err(|e| e.to_string())?;
    if !out.status.success() {
        let msg = String::from_utf8_lossy(&out.stderr);
        let msg = if msg.trim().is_empty() {
            String::from_utf8_lossy(&out.stdout).trim().to_string()
        } else {
            msg.trim().to_string()
        };
        return Err(if msg.is_empty() { "um 失败".into() } else { msg });
    }
    Ok(outdir.to_path_buf())
}

fn find_um() -> Option<PathBuf> {
    let name = if cfg!(windows) { "um.exe" } else { "um" };
    let here = env::current_exe().ok()?.parent()?.to_path_buf();
    for dir in [
        here.clone(),
        env::current_dir().unwrap_or_else(|_| PathBuf::from(".")),
    ] {
        let p = dir.join(name);
        if p.is_file() {
            return Some(p);
        }
    }
    let path = env::var_os("PATH")?;
    for dir in env::split_paths(&path) {
        let p = dir.join(name);
        if p.is_file() {
            return Some(p);
        }
    }
    None
}

fn mu_dir() -> PathBuf {
    if cfg!(windows) {
        std::env::var_os("LOCALAPPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("."))
            .join("music-unlock")
    } else {
        PathBuf::from(std::env::var_os("HOME").unwrap_or_default()).join(".local/share/music-unlock")
    }
}
