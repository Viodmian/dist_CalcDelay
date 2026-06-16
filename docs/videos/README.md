# DelayScope Intro Video

本目录包含 DelayScope 的项目介绍视频和对应演示稿。

- `DelayScope_intro.mp4`：约 81 秒的介绍视频，覆盖基本使用方式和 GCC-PHAT / 多段统计原理。
- `DelayScope_intro.pptx`：视频对应的 PowerPoint 演示稿，便于后续修改文案或重新导出。

重新生成视频：

```powershell
D:\Python314\python.exe -m pip install -r requirements_video.txt
D:\Python314\python.exe scripts\make_intro_video.py
```

生成脚本会先用 Pillow 生成 16:9 幻灯片帧，再调用本机 PowerPoint 导出 MP4。
