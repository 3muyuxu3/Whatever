import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { buildGraph, getBuildStatus, getProject, resetProject } from '../api/graph'
import {
  createSimulation,
  getEntities,
  getPrepareStatus,
  getProfilesRealtime,
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
  const [prepProfiles, setPrepProfiles] = useState([])
  const [prepTotal, setPrepTotal] = useState(null)
  const [logs, setLogs] = useState([])
  // 构建期间的临时 graph_id（用于实时可视化）；与 project.graph_id（用于解锁下一步）区分
  const [liveGraphId, setLiveGraphId] = useState(null)
  // 轮询定时器集合：组件卸载时统一清理，避免离开页面后仍在后台轮询并对已卸载组件 setState
  const pollTimersRef = useRef([])
  useEffect(() => () => pollTimersRef.current.forEach((id) => clearInterval(id)), [])

  const graphId = project?.graph_id
  // 可视化用：构建完成前使用临时 graph_id，建图过程中即可拉取并展示图谱逐渐填充。
  const vizGraphId = graphId || liveGraphId
  // 图谱是否已出现节点：Zep 抽取为异步，建图完成后仍可能有短暂索引延迟。
  // 因此在“出现节点前”持续自动刷新，避免建图结束后停留在“暂无图谱数据”。
  const [graphSeen, setGraphSeen] = useState(false)
  const { data: graphData, refresh } = useGraphData(vizGraphId, {
    // 建图中，或已有 graphId 但尚未拉到节点时，持续刷新（拿到节点即止）
    autoRefresh: building || (!!vizGraphId && !graphSeen),
    // 图谱读取有 15s 短时缓存，8s 轮询多数命中缓存（不额外增加 Zep 负载），
    // 缓存过期后即可较快拿到新抽取的实体，兼顾实时性与限流。
    refreshInterval: 8000,
  })
  // 一旦出现节点，标记已就绪并停止“空图轮询”
  useEffect(() => {
    if ((graphData?.nodes?.length || 0) > 0 && !graphSeen) setGraphSeen(true)
  }, [graphData, graphSeen])

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
              t('log.ontologyDone', {
                entities: p.ontology.entity_types.length,
                relations: (p.ontology.edge_types || []).length,
              }),
              'INFO',
            )
          }
          return // 本体就绪，停止轮询
        }
        if (p?.status === 'failed') {
          pushLog(t('log.ontologyFailed'), 'ERROR')
          return
        }
        if (!announced) {
          announced = true
          pushLog(t('log.ontologyGenerating'))
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
    pushLog(t('log.buildStarting'))
    try {
      const res = await buildGraph({ project_id: projectId })
      pushLog(t('log.buildTaskStarted', { task: res.data?.task_id || '' }))
      const timer = setInterval(async () => {
        try {
          const st = await getBuildStatus({ project_id: projectId })
          setBuildProgress(st.data?.progress || 0)
          // 拿到临时 graph_id 后，useGraphData 会自动轮询展示图谱逐渐填充
          if (st.data?.graph_id) setLiveGraphId(st.data.graph_id)
          pushLog(t('log.graphRefreshed', { progress: st.data?.progress || 0 }))
          if (st.data?.status === 'completed') {
            clearInterval(timer)
            setBuilding(false)
            const p = await getProject(projectId)
            setProject(p.data)
          } else if (st.data?.status === 'failed') {
            clearInterval(timer)
            setBuilding(false)
            pushLog(t('log.buildFailed', { error: st.data?.error || '' }), 'ERROR')
          }
        } catch (e) {
          clearInterval(timer)
          setBuilding(false)
        }
      }, 2000)
      pollTimersRef.current.push(timer)
    } catch (e) {
      setBuilding(false)
      pushLog(t('log.buildStartFailed'), 'ERROR')
    }
  }, [projectId, refresh, t])

  // 触发环境准备
  const handlePrepare = useCallback(async () => {
    setPreparing(true)
    setPrepProfiles([])
    pushLog(t('log.preparingEnv'))
    try {
      const created = await createSimulation({ project_id: projectId })
      const simId = created.data?.simulation_id || created.data?.id
      await prepareSimulation({ simulation_id: simId })
      const timer = setInterval(async () => {
        try {
          // 实时拉取生成中的人设，边生成边展示
          try {
            const pr = await getProfilesRealtime(simId)
            const list = pr.data?.profiles || []
            setPrepProfiles(list)
            if (pr.data?.total_expected) setPrepTotal(pr.data.total_expected)
            if (list.length) pushLog(t('log.profilesGenerated', { count: `${list.length}${pr.data?.total_expected ? '/' + pr.data.total_expected : ''}` }))
          } catch (e) { /* 忽略 */ }
          const st = await getPrepareStatus({ simulation_id: simId })
          setPrepProgress(st.data?.progress || 0)
          if (st.data?.status === 'completed') {
            clearInterval(timer)
            navigate(`/simulation/${simId}`)
          } else if (st.data?.status === 'failed') {
            clearInterval(timer)
            setPreparing(false)
            pushLog(t('log.prepareFailed'), 'ERROR')
          }
        } catch (e) {
          clearInterval(timer)
          setPreparing(false)
        }
      }, 2000)
      pollTimersRef.current.push(timer)
    } catch (e) {
      setPreparing(false)
    }
  }, [projectId, navigate, t])

  // 重置项目（重新构建图谱）
  const handleReset = useCallback(async () => {
    pushLog(t('log.resetProject'))
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
      pushLog(t('log.resetFailed'), 'ERROR')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, refresh, t])

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
            profiles={prepProfiles}
            total={prepTotal}
            onPrepare={handlePrepare}
          />
        </div>
      }
      consoleData={{
        title: t('process.systemDashboard'),
        id: `proj_${(projectId || '').slice(0, 12)}`,
        lines: logs,
      }}
    />
  )
}
