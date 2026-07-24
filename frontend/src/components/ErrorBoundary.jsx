import { Component } from 'react'
import { useTranslation } from 'react-i18next'

/**
 * 友好错误回退 UI（函数组件，便于使用 i18n）
 */
function Fallback({ onReset }) {
    const { t } = useTranslation()
    return (
        <div className="flex min-h-[40vh] flex-col items-center justify-center gap-4 p-8 text-center">
            <div className="text-2xl font-semibold text-neutral-200">
                {t('common.errorTitle', { defaultValue: '页面出现问题' })}
            </div>
            <p className="max-w-md text-sm text-neutral-400">
                {t('common.errorDesc', { defaultValue: '当前视图渲染失败，你可以重试或返回首页。' })}
            </p>
            <div className="flex gap-3">
                <button
                    type="button"
                    onClick={onReset}
                    className="rounded-lg bg-white px-5 py-2 text-sm font-medium text-black transition hover:bg-neutral-200"
                >
                    {t('common.retry', { defaultValue: '重试' })}
                </button>
                <a
                    href="/"
                    className="rounded-lg border border-white/20 px-5 py-2 text-sm font-medium text-neutral-200 transition hover:bg-white/10"
                >
                    {t('common.backHome', { defaultValue: '返回首页' })}
                </a>
            </div>
        </div>
    )
}

/**
 * ErrorBoundary —— React 错误边界
 *
 * 捕获子组件渲染期抛出的异常，避免整页崩溃（如 GraphPanel 的 D3 渲染遇到意外数据）。
 * 显示友好的回退界面并支持重试。
 */
export default class ErrorBoundary extends Component {
    constructor(props) {
        super(props)
        this.state = { hasError: false }
    }

    static getDerivedStateFromError() {
        return { hasError: true }
    }

    componentDidCatch(error, info) {
        // 输出到控制台便于排查
        // eslint-disable-next-line no-console
        console.error('ErrorBoundary caught:', error, info)
    }

    handleReset = () => this.setState({ hasError: false })

    render() {
        if (this.state.hasError) {
            return <Fallback onReset={this.handleReset} />
        }
        return this.props.children
    }
}
