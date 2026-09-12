//! 对照 Python 的 mg3d.py / kgg.py / qmc_ekey.parse_musicex_footer。

mod kgg;
mod mg3d;
mod musicex;

pub use kgg::{default_roots, find_db, KggPaths};
pub use mg3d::decrypt as mg3d_decrypt;
pub use musicex::{parse_musicex_footer, MusicexFooter};

pub const OUT_NAME: &str = "已解锁";
