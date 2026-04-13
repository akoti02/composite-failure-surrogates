@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
cd /d "C:\Users\akoti\University RP3 - Composite Failure Surrogate Modelling\rp3-app\src-tauri"
cargo build 2>&1
