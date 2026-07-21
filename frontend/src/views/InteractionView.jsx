import { useParams } from 'react-router-dom'
import Step5Interaction from '../components/Step5Interaction'

/**
 * InteractionView —— 深度互动页（Step 5）
 */
export default function InteractionView() {
  const { reportId } = useParams()
  return (
    <div className="mx-auto max-w-6xl px-6 py-8 md:px-12">
      <Step5Interaction reportId={reportId} />
    </div>
  )
}
