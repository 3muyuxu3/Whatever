// 集中管理散落各处的常量：GitHub 入口、外部图标 URL、报告检索工具元数据。
// 避免在多个组件中重复定义，修改时只需改这一处。

// GitHub 仓库入口
export const GITHUB_URL = 'https://github.com/3muyuxu3/muyuxu'

// icons8 白色 GitHub 图标（供导航栏 / 页脚使用）
export const ICON_GITHUB = 'https://img.icons8.com/ios-glyphs/90/ffffff/github.png'

// 报告生成期间展示的 4 种检索工具（key 走 i18n，icon 为 icons8 URL）
export const TOOLS = [
    { key: 'toolInsight', icon: 'https://img.icons8.com/ios/50/7c3aed/idea.png' },
    { key: 'toolPanorama', icon: 'https://img.icons8.com/ios/50/0ea5e9/globe--v1.png' },
    { key: 'toolQuick', icon: 'https://img.icons8.com/ios/50/f59e0b/flash-on.png' },
    { key: 'toolInterview', icon: 'https://img.icons8.com/ios/50/059669/conference-call.png' },
]

// 工具名 -> 展示元数据（用于真实 ReACT 调用轨迹的着色与文案）
export const TOOL_META = {
    QuickSearch: { color: '#f59e0b', key: 'toolQuick' },
    PanoramaSearch: { color: '#0ea5e9', key: 'toolPanorama' },
    InsightForge: { color: '#7c3aed', key: 'toolInsight' },
    InterviewAgents: { color: '#059669', key: 'toolInterview' },
}
