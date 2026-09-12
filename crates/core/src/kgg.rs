//! 酷狗 KGMusicV3.db 定位，对照 kgg.py。Windows 只扫酷狗自己的目录。

use std::fs;
use std::path::{Path, PathBuf};

pub const DB_NAME: &str = "KGMusicV3.db";

const SKIP: &[&str] = &[
    "windows", "system32", "syswow64", "winsxs", "node_modules", ".git", "$recycle.bin", "temp",
    "tmp", "steam", "steamapps", ".steam",
];

#[derive(Clone, Debug)]
pub struct KggPaths {
    pub mu_dir: PathBuf,
    pub roots: Vec<PathBuf>,
}

impl KggPaths {
    pub fn conf(&self) -> PathBuf {
        self.mu_dir.join("kgg_db_path.txt")
    }
}

pub fn default_roots() -> Vec<PathBuf> {
    if cfg!(windows) {
        let roaming = std::env::var_os("APPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|| dirs_fallback("AppData/Roaming"));
        let local = std::env::var_os("LOCALAPPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|| dirs_fallback("AppData/Local"));
        ["KuGou8", "Kugou8", "KuGou"]
            .into_iter()
            .flat_map(|name| [roaming.join(name), local.join(name)])
            .collect()
    } else {
        ["~/.cxoffice", "~/.wine", "~/.local/share/wineprefixes", "~/Games", "~/Applications"]
            .into_iter()
            .map(expand_home)
            .collect()
    }
}

fn dirs_fallback(rest: &str) -> PathBuf {
    expand_home("~").join(rest)
}

fn expand_home(p: &str) -> PathBuf {
    if let Some(rest) = p.strip_prefix("~/") {
        let home = std::env::var_os("HOME")
            .or_else(|| std::env::var_os("USERPROFILE"))
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("."));
        return home.join(rest);
    }
    PathBuf::from(p)
}

fn remember(conf: &Path, path: &Path) -> PathBuf {
    if let Some(parent) = conf.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let _ = fs::write(conf, path.to_string_lossy().as_bytes());
    path.to_path_buf()
}

pub fn find_db(paths: &KggPaths) -> Option<PathBuf> {
    let conf = paths.conf();
    if let Ok(saved) = fs::read_to_string(&conf) {
        let p = PathBuf::from(saved.trim());
        if p.is_file() {
            return Some(p);
        }
    }
    for root in &paths.roots {
        if !root.is_dir() {
            continue;
        }
        if let Some(found) = walk(root, 0) {
            return Some(remember(&conf, &found));
        }
    }
    None
}

fn walk(dir: &Path, depth: usize) -> Option<PathBuf> {
    let rd = fs::read_dir(dir).ok()?;
    let mut dirs = Vec::new();
    for ent in rd.flatten() {
        let name = ent.file_name();
        let name_s = name.to_string_lossy();
        let path = ent.path();
        if path.is_file() && name_s == DB_NAME {
            return Some(path);
        }
        if path.is_dir() && !SKIP.iter().any(|s| name_s.eq_ignore_ascii_case(s)) {
            dirs.push(path);
        }
    }
    if depth >= 6 {
        return None;
    }
    for d in dirs {
        if let Some(found) = walk(&d, depth + 1) {
            return Some(found);
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn first_scan_returns_the_path() {
        let tmp = tempdir().unwrap();
        let nested = tmp.path().join("KuGou8");
        fs::create_dir(&nested).unwrap();
        let db = nested.join(DB_NAME);
        fs::write(&db, b"x").unwrap();
        let confdir = tmp.path().join("conf");
        let found = find_db(&KggPaths {
            mu_dir: confdir.clone(),
            roots: vec![tmp.path().to_path_buf()],
        })
        .unwrap();
        assert_eq!(found, db);
        assert_eq!(fs::read_to_string(confdir.join("kgg_db_path.txt")).unwrap(), db.to_string_lossy());
    }

    #[test]
    fn missing_db_returns_none() {
        let tmp = tempdir().unwrap();
        assert!(find_db(&KggPaths {
            mu_dir: tmp.path().join("conf"),
            roots: vec![tmp.path().to_path_buf()],
        })
        .is_none());
    }

    #[test]
    fn windows_roots_are_kugou_not_whole_appdata() {
        // 逻辑对照 kgg.default_roots：Windows 条目都以酷狗目录结尾。
        let roots = default_roots();
        if cfg!(windows) {
            assert!(roots.iter().all(|p| {
                p.ends_with("KuGou8") || p.ends_with("Kugou8") || p.ends_with("KuGou")
            }));
        } else {
            assert!(roots.iter().any(|p| p.ends_with("wine") || p.ends_with(".wine")));
        }
    }
}
