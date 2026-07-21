import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getProject } from '../api/graph'
import Step1GraphBuild from '../components/Step1GraphBuild'
import Step2EnvSetup from '../components/Step2EnvSetup'

/**
 * MainView —— 主流程页（Step 1-2：图谱构建 + 环境搭建）
 */
export default function MainView() {
  const { projectId } = useParams()
  const [project, setProject] = useState({ id: projectId })

  useEffect(() => {
    getProject(projectId)
      .then((res) => setProject(res.data || { id: projectId }))
      .catch(() => setProject({ id: projectId }))
  }, [projectId])

  return (
    <div className="mx-auto max-w-6xl space-y-16 px-6 py-8 md:px-12">
      <Step1GraphBuild project={project} />
      <Step2EnvSetup project={project} />
    </div>
  )
}
