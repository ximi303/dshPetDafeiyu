#include "storage.h"

#include <LittleFS.h>
#include <SD.h>
#include <SPI.h>

namespace pet::storage {

static fs::FS* s_fs = nullptr;
static String s_root;
static std::vector<PackEntry> s_packs;

fs::FS* mount() {
    if (s_fs) {
        return s_fs;
    }

    if (kBackend == Backend::Flash) {
        // 按分区 label 挂载（partitions.csv 里的 "storage"）。
        // 注意第 4 个参数是 partitionLabel，不是挂载点 —— 写错会挂到默认分区上。
        if (!LittleFS.begin(false, kFlashMount, kFlashMaxOpenFiles, kFlashPartLabel)) {
            return nullptr;
        }
        s_fs = &LittleFS;
        s_root = String(kFlashMount) + kPackRoot;
    } else {
        if (!SD.begin(kSdCsPin, SPI, kSdSpiHz, kSdMount)) {
            return nullptr;
        }
        s_fs = &SD;
        s_root = String(kSdMount) + kPackRoot;
    }

    return s_fs;
}

bool mounted() {
    return s_fs != nullptr;
}

Backend activeBackend() {
    return kBackend;
}

const char* packRootPath() {
    return s_root.c_str();
}

static void scanDir(fs::FS& fs, const String& dir, std::vector<PackEntry>& out) {
    File root = fs.open(dir, "r");
    if (!root) {
        return;
    }
    if (!root.isDirectory()) {
        root.close();
        return;
    }

    while (true) {
        File f = root.openNextFile();
        if (!f) {
            break;
        }
        const String name = String(f.name());
        const String child = dir + "/" + name;
        if (f.isDirectory()) {
            scanDir(fs, child, out);
        } else if (name.endsWith(".petpack")) {
            PackEntry e;
            e.path = child;
            // dir 形如 /storage/packs/<分类>，最后一段就是分类名
            const int slash = dir.lastIndexOf('/');
            e.group = (slash >= 0) ? dir.substring(slash + 1) : String("");
            // 段名 = 文件名去掉 .petpack
            const int dot = name.lastIndexOf('.');
            e.name = (dot > 0) ? name.substring(0, dot) : name;
            out.push_back(e);
        }
        f.close();
    }
    root.close();
}

size_t scanPacks() {
    s_packs.clear();
    if (!mount()) {
        return 0;
    }
    scanDir(*s_fs, String(packRootPath()), s_packs);
    return s_packs.size();
}

const std::vector<PackEntry>& packs() {
    return s_packs;
}

}  // namespace pet::storage
