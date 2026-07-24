import { createContext, useContext, useMemo, useState } from 'react'

/**
 * UploadContext —— 待上传文件与预测需求的全局状态
 *
 * 首页选择文件 / 填写预测需求后，跳转到处理流程页时复用这些状态，
 * 避免通过路由参数传递大对象。
 */
const UploadContext = createContext(null)

export function UploadProvider({ children }) {
    const [files, setFiles] = useState([]) // 待上传的种子文件（File 对象数组，支持多文件）
    const [requirement, setRequirement] = useState('') // 预测需求描述文本

    // 重置为初始状态
    const reset = () => {
        setFiles([])
        setRequirement('')
    }

    // memo 化 value，避免 Provider 每次渲染都创建新对象引用导致所有消费组件重渲染
    const value = useMemo(
        () => ({ files, setFiles, requirement, setRequirement, reset }),
        [files, requirement],
    )

    return (
        <UploadContext.Provider value={value}>
            {children}
        </UploadContext.Provider>
    )
}

// 便捷 Hook：在组件中读取/更新上传状态
export function useUpload() {
    const ctx = useContext(UploadContext)
    if (!ctx) {
        throw new Error('useUpload 必须在 <UploadProvider> 内部使用')
    }
    return ctx
}

export default UploadContext
