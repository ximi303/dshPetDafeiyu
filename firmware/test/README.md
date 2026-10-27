# 固件单测（预留）

PlatformIO 用 Unity 框架，命令：

```powershell
pio test -e esp32-s3-n16r8        # 需要真机
pio test -e native                # 纯逻辑测试，不需要硬件
```

## 为什么值得先测 petpack

`petpack.cpp` 是**纯逻辑**：不依赖屏、不依赖解码库、不依赖 PSRAM。
它唯一做的事就是「读 22 字节头 → 读偏移表 → 按索引取帧」。

所以最划算的做法是加一个 `native` 环境（跑在 PC 上），
直接拿真实的 `.petpack` 文件喂进去，断言：

- magic / version / 宽高 / 帧数解析正确
- `frameRange()` 算出的相邻偏移能首尾相接
- `readFrame()` 读出的每帧以 `FFD8` 开头、以 `FFD9` 结尾
- 越界索引、缓冲不足、损坏文件都返回约定的负错误码

这些在 PC 上几毫秒就能跑完，不用烧板子、不用看串口。

## 加 native 环境时要在 platformio.ini 里补

```ini
[env:native]
platform = native
test_framework = unity
build_flags = -std=c++17
```

注意 `petpack.cpp` 依赖 `fs::FS` 与 `File`，native 下没有 Arduino 的 FS 实现，
需要写一个简单的桩（把文件读进内存即可），或者把纯解析部分抽成不依赖 `File` 的函数。
