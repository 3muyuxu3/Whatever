import { useParams } from 'react-router-dom'
import Step4Report from '../components/Step4Report'

/**
 * ReportView —— 报告页（Step 4）
 * 路由参数携带模拟 ID，用于触发报告生成并展示结果。
 */
export default function ReportView() {
  const { reportId } = useParams()
  return (
    <div className="mx-auto max-w-6xl px-6 py-8 md:px-12">
      <Step4Report simulationId={reportId} />
    </div>
  )
}
