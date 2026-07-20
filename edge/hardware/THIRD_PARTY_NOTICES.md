# 第三方代码与参考资料声明

模块 1 在实现真实传感器适配器时使用或参考了以下 MIT 许可项目。项目自身代码的授权状态以仓库根目录的许可证政策为准。

## Adafruit CircuitPython MLX90640

- 仓库：`https://github.com/adafruit/Adafruit_CircuitPython_MLX90640`
- 核对 commit：`6a537df6af2fce6ad301e2022a7084da9b25af19`
- 许可证：MIT
- 使用方式：在 `pyproject.toml` 中声明 `adafruit-circuitpython-mlx90640` 为可选硬件依赖，通过其公开 API 读取传感器；本仓库未复制该项目的低层驱动源码。

```text
The MIT License (MIT)

Copyright (c) 2019 ladyada for Adafruit Industries

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## csRon/HLK-LD2450

- 仓库：`https://github.com/csRon/HLK-LD2450`
- 核对 commit：`1b65a026873ab2db3d22d3b3bb99ef16fbcdd4f0`
- 许可证：MIT
- 使用方式：`drivers/ld2450.py` 的报告帧边界、字段布局和符号位解析参考该项目及其包含的厂商串口协议资料，并在本项目统一驱动接口下重新实现流式解析、错误隔离和健康统计。

```text
MIT License

Copyright (c) 2024 Ron Martin

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

检索阶段还查看了其他开源实现，但没有把 GPL 或 AGPL 代码复制到本模块。
