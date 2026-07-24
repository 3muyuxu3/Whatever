/**
 * Logo —— SimulMirror 品牌标识（矢量）
 *
 * 「预测水晶球」概念：一枚立在底座上的透明水晶球，球心是绿色的「未来/世界」核心
 * （品牌色 #32F08C），配以高光玻璃质感——寓意观察并推演未来。
 * 主体使用 currentColor，随所在容器文字颜色自适应——深色页头显白、浅色文档显深，
 * 一枚标识明暗两套主题通用；绿色为固定强调色。
 */
export default function Logo({ className = '', title = 'SimulMirror' }) {
    return (
        <svg
            viewBox="0 0 32 32"
            fill="none"
            role="img"
            aria-label={title}
            className={className}
            xmlns="http://www.w3.org/2000/svg"
        >
            {/* 玻璃球体（半透明球体 + 边缘） */}
            <circle cx="16" cy="12.5" r="7" fill="currentColor" fillOpacity="0.16" />
            <circle cx="16" cy="12.5" r="7" stroke="currentColor" strokeWidth="1.6" />
            {/* 球中的未来 / 世界核心 */}
            <circle cx="16" cy="12.5" r="2.6" fill="#32F08C" />
            {/* 玻璃高光 */}
            <circle cx="12.6" cy="9.4" r="1.05" fill="currentColor" />
            {/* 底座 */}
            <rect x="14.4" y="19.2" width="3.2" height="3.2" fill="currentColor" />
            <rect x="9.5" y="22" width="13" height="2.6" rx="1.3" fill="currentColor" />
        </svg>
    )
}
