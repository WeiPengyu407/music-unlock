//! qmc-decoder CLI：QQ 音乐加密文件（QMC1/QMC2）命令行解密器。
//! 用法: qmc-decoder [--ekey KEY] <输入文件> <输出目录>
//! 音乐解锁 App 以 `--ekey` 模式调用（musicex 新格式，ekey 由 QQ 登录态换得）。

use qmc_decoder::{decrypt_file, determine_output_path, Format};
use std::path::Path;
use std::process::exit;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut ekey: Option<String> = None;
    let mut positional: Vec<String> = Vec::new();
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--ekey" => {
                i += 1;
                ekey = args.get(i).cloned();
            }
            "--fetch-ekey" => {} // lib 默认行为，兼容旧调用
            s => positional.push(s.to_string()),
        }
        i += 1;
    }
    if positional.len() != 2 {
        eprintln!("QQ Music encrypted file decoder");
        eprintln!("用法: qmc-decoder [--ekey KEY] <输入文件> <输出目录>");
        exit(2);
    }
    let input = Path::new(&positional[0]);
    let outdir = Path::new(&positional[1]);
    let ext = input
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase();
    let format = match Format::from_extension(&ext) {
        Some(f) => f,
        None => {
            eprintln!("不支持的格式: {ext}");
            exit(1);
        }
    };
    std::fs::create_dir_all(outdir).expect("创建输出目录失败");
    let output = determine_output_path(input, Some(outdir), format);
    match decrypt_file(input, &output, format, ekey.as_deref(), ekey.is_none()) {
        Ok(r) => println!("{} -> {}", r.input_path.display(), r.output_path.display()),
        Err(e) => {
            eprintln!("解密失败: {e}");
            exit(1);
        }
    }
}
