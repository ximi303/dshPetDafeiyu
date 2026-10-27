// 下载一个完整版 ffmpeg（当前系统里的 ffmpeg 是精简编译版，不能输出 JPEG 帧序列）
// 用法：node tools/pipeline/download-ffmpeg.mjs
// 产物：tools/ffmpeg.zip —— 解压出 ffmpeg-<版本>/ 目录，重命名为 ffmpeg 放到 tools/ 下，
//       最终可用路径为 tools/ffmpeg/bin/ffmpeg.exe
import fs from 'node:fs';
import path from 'node:path';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { fileURLToPath } from 'node:url';

// 路径全部相对本脚本定位：本脚本在 tools/pipeline/ 下，往上一级是 tools/，往上两级是项目根
const here = path.dirname(fileURLToPath(import.meta.url));
const projDir = path.resolve(here, '..', '..');
const toolsDir = path.resolve(here, '..');            // tools/
const zipPath = path.join(toolsDir, 'ffmpeg.zip');

const CANDIDATES = [
  'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip',
  'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n7.1-latest-win64-gpl-7.1.zip',
  'https://github.com/GyanD/codexffmpeg/releases/download/7.1/ffmpeg-7.1-essentials_build.zip',
];

async function tryDownload(url) {
  const t0 = Date.now();
  const res = await fetch(url, { redirect: 'follow' });
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status} ${res.statusText}`);
  const total = Number(res.headers.get('content-length') || 0);
  let got = 0;
  let lastLog = 0;
  const ws = fs.createWriteStream(zipPath);
  const body = Readable.fromWeb(res.body);
  body.on('data', (chunk) => {
    got += chunk.length;
    const now = Date.now();
    if (now - lastLog > 3000) {
      lastLog = now;
      const pct = total ? ((got / total) * 100).toFixed(1) + '%' : '';
      console.log(`  ${(got / 1048576).toFixed(1)} MB ${pct}`);
    }
  });
  await pipeline(body, ws);
  console.log(`  下载完成 ${(got / 1048576).toFixed(1)} MB，用时 ${((Date.now() - t0) / 1000).toFixed(0)}s`);
}

fs.mkdirSync(toolsDir, { recursive: true });
let ok = false;
for (const url of CANDIDATES) {
  try {
    console.log('尝试:', url);
    await tryDownload(url);
    ok = true;
    break;
  } catch (e) {
    console.log('  失败:', e.message);
    try { fs.rmSync(zipPath, { force: true }); } catch {}
  }
}
if (!ok) {
  console.error('所有下载源都失败了');
  process.exit(1);
}
console.log('ZIP 已保存到', zipPath);
console.log('解压后把 ffmpeg-<版本>/ 重命名为 ffmpeg 放到 tools/ 下，确认存在：',
            path.join(toolsDir, 'ffmpeg', 'bin', 'ffmpeg.exe'));
