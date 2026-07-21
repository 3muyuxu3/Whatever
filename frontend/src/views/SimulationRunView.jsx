import { useParams, useSearchParams } from 'react-router-dom'
import Step3Simulation from '../components/Step3Simulation'

/**
 * SimulationRunView —— 模拟运行页（Step 3）
 * 支持通过查询参数 ?maxRounds 指定最大模拟轮数。
 */
export default function SimulationRunView() {
  const { simulationId } = useParams()
  const [searchParams] = useSearchParams()
  const maxRounds = Number(searchParams.get('maxRounds')) || 10

  return (
    <div className="mx-auto max-w-6xl px-6 py-8 md:px-12">
      <Step3Simulation
        simulationId={simulationId}
        graphId={simulationId}
        maxRounds={maxRounds}
      />
    </div>
  )
}
