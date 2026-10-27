<!-- Revelation Ray Tracing 分支修改，2026-10-27。Apache-2.0。 -->
# Revelation Ray Tracing

**简体中文** | [English](README.md)

基于 [HaringPro/Revelation](https://github.com/HaringPro/Revelation) 的 Minecraft 光影分支，增加局部多光源软件光追、染色玻璃透光、可调手持光源与手电筒。此分支独立维护。

## 下载和安装

**当前版本：v9.3 光源调色与手电筒。** 从 [发布页](https://github.com/ikunkk02-afk/Revelation-Ray-Tracing/releases/latest) 下载 `Revelation-RT-v9.3-LightControls.zip`，不用解压，放进游戏实例的 `shaderpacks` 文件夹，在 Iris 中选择。GitHub 自动生成的 Source code 压缩包用于开发。

目标环境：Minecraft **1.21.1 Fabric**、Iris **1.8.14-beta.1**、OpenGL **4.6**。离线 GPU 检查使用 RTX 5060 Laptop。其他硬件、Iris 版本和扩展模组组合需要自行测试。**不支持 OptiFine。**

建议从“高”或“极高”开始，按帧率调整；“光线追踪”为负载最高档，包内默认“极高”。这里使用软件光追，不调用硬件 RTX 光追核心。

## 功能与设置

- 方块和手持光源默认使用稳定单中心投影，支持镂空遮挡和染色玻璃透射。
- 多光源照明、保边的半分辨率局部光计算，以及材质解释修正。
- 六档画质：原版默认、低、中、高、极高、光线追踪。
- 光影设置 → **光源与手电筒**：独立调整方块、手持光源的亮度，选择自定义 RGB 颜色。
- 可把普通、灵魂、红石火把变为跟随视角的手电筒，主副手均支持，提供张角、边缘柔和度和距离设置。其他手持发光物仍为全向照明。

默认关闭自定义颜色和手电筒模式；切换画质不会覆盖这些个人设置。白色手电筒示例：开启手电筒和自定义手持光色，RGB 都设为 1，手持亮度从 1 开始调整。本版为表面聚光照明，不新增空气中的可见光柱。

[详细设置说明](docs/RT_V9_3_LIGHT_CONTROLS.zh-CN.md) · [单投影阴影说明](docs/RT_V9_2_PROJECTION.zh-CN.md) · [分支修改记录](MODIFICATIONS.md)

## 验证与限制

随发布保留离线结果：656 项编译/链接、414 项行为检查（622,592 条射线）、21 项光源控制、10 项单投影检查，以及接缝、密集光源和本机 Iris 元数据检查。这些检查不代表 Minecraft 帧率或所有场景画面质量；游戏内测试由用户完成。

局部照明有场景网格范围限制，间接光依赖屏幕信息。默认阴影是点光源近似；实验面积光选项可能出现多重投影。保留上游 Voxy、Distant Horizons、Physics Mod、Super Resolution、HDR 的集成代码，但本 RT 版本未验证这些组合。

## 构建

使用 Python 3.10+，从标签源码打包并验证随附报告：

```sh
python scripts/build_release.py --output-dir dist
```

光影包包含 GLSL 源码和素材，由 Iris 在运行时编译。[GPU 检查步骤与历史对照包要求](validation/README.md) 说明如何重新验证；需要兼容的 OpenGL 环境，部分对比检查还需旧开发包。Iris 元数据检查另需 Java 21、目标 Iris 与依赖 JAR。[本次发布说明](docs/RELEASE_v9.3.md)。

## 原作者与致谢

- [HaringPro](https://github.com/HaringPro)：Revelation 原作者。
- [Yong-Xin Mo](https://github.com/moyongxin)：代码贡献与技术指导。
- [GeForceLegend](https://github.com/GeForceLegend)：代码贡献与调试。
- [FactoriZation](https://github.com/FactoriZation000)：开发协助与 AMD 显卡测试。
- [NASA Scientific Visualization Studio](https://svs.gsfc.nasa.gov)：星空图与月球图像素材。

## 许可证

沿用原仓库 **[Apache License 2.0](LICENSE)**，包括本分支新增和修改的 RT 代码。保留原作者署名；第三方组件遵循各自原有声明，参见 [NOTICE](NOTICE)、[第三方许可索引](THIRD_PARTY_NOTICES.md)、[修改记录](MODIFICATIONS.md)。本项目是修改分支，不代表原作者背书。
