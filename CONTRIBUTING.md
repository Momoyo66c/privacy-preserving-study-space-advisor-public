# 贡献与协作规则

## 分支命名

每个模块使用独立分支：

```text
module1/<short-description>
module2/<short-description>
module3/<short-description>
module4/<short-description>
docs/<short-description>
fix/<short-description>
```

不要直接在 `main` 上开发。一个 Pull Request 只处理一个清晰目标。

## 开始工作

```bash
git switch main
git pull --ff-only
git switch -c module2/feature-pipeline
```

开发前阅读共享契约和对应模块规格。需要改变跨模块接口时，先在 Issue 中说明影响，再同时更新契约、Schema、fixture 和测试。

## 提交规范

建议使用：

```text
feat(module1): add MLX90640 adapter
feat(module3): add observation endpoint
test(module2): cover missing radar features
docs: clarify thermal preview contract
fix(module4): keep ranking when LLM times out
```

提交中禁止包含：

- `.env`、API Key、密码和令牌。
- 原始语音、RGB 图像或个人身份数据。
- 大型数据集、虚拟环境、构建目录和模型缓存。
- 与当前模块无关的格式化或重写。

## Pull Request 要求

- 描述完成了什么以及为什么。
- 列出测试命令和结果。
- 说明是否改变共享契约。
- 提供必要的截图、API 示例或硬件测试记录。
- 指定至少一位其他成员评审。
- 所有自动检查通过后再合并。

合并优先使用 Squash and merge，使 `main` 历史保持清晰。

## 解决冲突

```bash
git fetch origin
git rebase origin/main
# 解决冲突并测试
git push --force-with-lease
```

仅对自己的功能分支使用 `--force-with-lease`，不要强推 `main`。
