import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { buildGraph, getBuildStatus, getProject, resetProject } from '../api/graph'
import {
  createSimulation,
  getEntities,
  getPrepareStatus,
  prepareSimulation,
} from '../api/simulation'
import { useGraphData } from '../hooks/useGraphData'
import ProcessLayout from '../components/ProcessLayout'
import GraphPanel from '../components/GraphPanel'
import Step1GraphBuild from '../components/Step1GraphBuild'
import Step2EnvSetup from '../components/Step2EnvSetup'

/**
 * MainView —— 流程页 Step 1-2（图谱构建 + 环境搭建）
 */
export default function MainView() {
  const { projectId } = useParams()
  const { t } = useTranslation()
  const navigate = useNavigate()

  const [project, setProject] = useState({ id: projectId })
  const [building, setBuilding] = useState(false)
  const [buildProgress, setBuildProgress] = useState(0)
  const [entities, setEntities] = useState([])
  const [preparing, setPreparing] = useState(false)
  const [prepProgress, setPrepProgress] = useState(0)
  const [logs, setLogs] = useState([])
  // 构建期间的临时 graph_id（用于实时可视化）；与 project.graph_id（用于解锁下一步）区分
  const [liveGraphId, setLiveGraphId] = useState(null)

  const graphId = project?.graph_id
  // 可视化用：构建完成前使用临时 graph_id，建图过程中即可拉取并展示图谱逐渐填充
  const vizGraphId = graphId || liveGraphId
  const { data: graphData, refresh } = useGraphData(vizGraphId, {
    autoRefresh: building,
    refreshInterval: 6000,
  })

  const pushLog = (text, level) =>
    setLogs((l) => [...l.slice(-60), { time: new Date().toLocaleTimeString(), level, text }])

  // 加载项目；本体在后台异步生成，需持续轮询直到就绪，
  // 否则会“卡住”停留在初始快照上，必须手动刷新页面才更新。
  useEffect(() => {
    let timer = null
    let cancelled = false
    let announced = false // 是否已提示“生成中”

    const isReady = (p) => (p?.ontology?.entity_types || []).length > 0

    const poll = async () => {
      try {
        const res = await getProject(projectId)
        if (cancelled) return
        const p = res.data || { id: projectId }
        setProject(p)

        if (isReady(p)) {
          if (announced) {
            pushLog(
              `本体生成完成：${p.ontology.entity_types.length} 个实体类型，` +
              `${(p.ontology.edge_types || []).length} 个关系类型`,
              'INFO',
            )
          }
          return // 本体就绪，停止轮询
        }
        if (p?.status === 'failed') {
          pushLog('本体生成失败', 'ERROR')
          return
        }
        if (!announced) {
          announced = true
          pushLog('正在生成本体 …')
        }
        timer = setTimeout(poll, 2000)
      } catch {
        if (cancelled) return
        timer = setTimeout(poll, 2000)
      }
    }

    poll()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  // 图谱就绪后加载实体
  useEffect(() => {
    if (!graphId) return
    getEntities(graphId)
      .then((res) => setEntities(res.data?.entities || []))
      .catch(() => setEntities([]))
  }, [graphId])

  const stats = {
    nodes: graphData?.nodes?.length || 0,
    edges: graphData?.edges?.length || 0,
    schema: (project?.ontology?.entity_types || []).length,
  }

  // 触发图谱构建
  const handleBuild = useCallback(async () => {
    setBuilding(true)
    pushLog('正在启动图谱构建 …')
    try {
      const res = await buildGraph({ project_id: projectId })
      pushLog(`图谱构建任务已启动 … Task: ${res.data?.task_id || ''}`)
      const timer = setInterval(async () => {
        try {
          const st = await getBuildStatus({ project_id: projectId })
          setBuildProgress(st.data?.progress || 0)
          // 拿到临时 graph_id 后，useGraphData 会自动轮询展示图谱逐渐填充
          if (st.data?.graph_id) setLiveGraphId(st.data.graph_id)
          pushLog(`Graph refreshed, progress: ${st.data?.progress || 0}%`)
          if (st.data?.status === 'completed') {
            clearInterval(timer)
            setBuilding(false)
            const p = await getProject(projectId)
            setProject(p.data)
          } else if (st.data?.status === 'failed') {
            clearInterval(timer)
            setBuilding(false)
            pushLog(`构建失败：${st.data?.error || ''}`, 'ERROR')
          }
        } catch (e) {
          clearInterval(timer)
          setBuilding(false)
        }
      }, 2000)
    } catch (e) {
      setBuilding(false)
      pushLog('构建启动失败', 'ERROR')
    }
  }, [projectId, refresh])

  // 触发环境准备
  const handlePrepare = useCallback(async () => {
    setPreparing(true)
    pushLog('准备模拟环境 …')
    try {
      const created = await createSimulation({ project_id: projectId })
      const simId = created.data?.simulation_id || created.data?.id
      await prepareSimulation({ simulation_id: simId })
      const timer = setInterval(async () => {
        try {
          const st = await getPrepareStatus({ simulation_id: simId })
          setPrepProgress(st.data?.progress || 0)
          if (st.data?.status === 'completed') {
            clearInterval(timer)
            navigate(`/simulation/${simId}`)
          } else if (st.data?.status === 'failed') {
            clearInterval(timer)
            setPreparing(false)
          }
        } catch (e) {
          clearInterval(timer)
          setPreparing(false)
        }
      }, 2000)
    } catch (e) {
      setPreparing(false)
    }
  }, [projectId, navigate])

  // 重置项目（重新构建图谱）
  const handleReset = useCallback(async () => {
    pushLog('重置项目状态 …')
    try {
      await resetProject(projectId)
      const p = await getProject(projectId)
      setProject(p.data || { id: projectId })
      setEntities([])
      setBuilding(false)
      setBuildProgress(0)
      setLiveGraphId(null)
      refresh()
    } catch (e) {
      pushLog('重置失败', 'ERROR')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, refresh])

  const step = project?.graph_id ? 2 : 1
  const stepName = project?.graph_id ? t('steps.step2') : t('steps.step1')
  const status = building
    ? { label: t('process.status.buildingGraph'), tone: 'orange' }
    : project?.graph_id
      ? { label: t('process.status.ready'), tone: 'green' }
      : { label: t('process.status.processing'), tone: 'orange' }

  return (
    <ProcessLayout
      step={step}
      stepName={stepName}
      status={status}
      defaultView="split"
      primary={
        <GraphPanel
          data={graphData}
          graphId={vizGraphId}
          memoryLabel={building ? t('process.memoryUpdating') : undefined}
          onRefresh={refresh}
        />
      }
      secondary={
        <div className="pb-2">
          <Step1GraphBuild
            project={project}
            building={building}
            progress={buildProgress}
            stats={stats}
            onBuild={handleBuild}
            onReset={handleReset}
          />
          <Step2EnvSetup
            project={project}
            entities={entities}
            preparing={preparing}
            progress={prepProgress}
            onPrepare={handlePrepare}
          />
        </div>
      }
      consoleData={{
        title: 'SYSTEM DASHBOARD',
        id: `proj_${(projectId || '').slice(0, 12)}`,
        lines: logs,
      }}
    />
  )
}
