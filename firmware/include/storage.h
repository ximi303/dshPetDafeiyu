#pragma once

// ============================================================
// 存储后端 —— 阶段 1 用 Flash（LittleFS），阶段 2 切 SD 卡
//
// 切换只改 platformio.ini 的 -DSTORAGE_BACKEND=0|1，
// 上层拿到的永远是同一个 fs::FS&，所以 petpack / player 一行都不用动。
// ============================================================

#include <cstdint>
#include <vector>

#include <Arduino.h>
#include <FS.h>

#include "config.h"

namespace pet::storage {

struct PackEntry {
    String path;   // 完整路径，如 /storage/packs/待机/待机呼吸休闲.petpack
    String group;  // 分类目录名：待机 / 点击回应 / 随机-玩耍 / ...
    String name;   // 段名，不含扩展名
};

// 挂载 config.h 里指定的后端，成功返回文件系统指针，失败返回 nullptr
fs::FS* mount();
bool    mounted();

Backend      activeBackend();
const char*  packRootPath();  // 挂载点 + /packs，如 /storage/packs

// 递归扫描 packRootPath() 下所有 *.petpack，填索引
size_t                      scanPacks();
const std::vector<PackEntry>& packs();

}  // namespace pet::storage
