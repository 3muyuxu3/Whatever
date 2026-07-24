import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { useThreeScene } from '../hooks/useThreeScene'

const MODEL_URL = '/models/LittlestTokyo.glb'

// 模块级缓存：整站仅解码一次 GLB。
// 关键：DRACO 解码放在组件生命周期之外，避免 React StrictMode 开发模式双挂载时，
// 首个 mount 的清理调用 draco.dispose() 中止解码 worker，导致模型永远卡在「加载中」。
// 解码完成后立即释放 DRACOLoader；失败则清空缓存以便重试。
let modelPromise = null
function loadTokyoModel() {
    if (!modelPromise) {
        modelPromise = new Promise((resolve, reject) => {
            const draco = new DRACOLoader().setDecoderPath('/draco/')
            const loader = new GLTFLoader()
            loader.setDRACOLoader(draco)
            loader.load(
                MODEL_URL,
                (gltf) => { draco.dispose(); resolve(gltf) },
                undefined,
                (err) => { draco.dispose(); modelPromise = null; reject(err) },
            )
        })
    }
    return modelPromise
}

/**
 * TokyoDiorama —— 「会呼吸的镜像世界」交互式 3D 展示
 *
 * 加载 DRACO 压缩的 Littlest Tokyo 动画模型（GLB），自动播放关键帧动画，
 * 以 RoomEnvironment 提供影棚级环境光，OrbitControls 支持拖动环视 + 缓速自转。
 * 复用 useThreeScene：StrictMode 安全、离开视口暂停、尊重 reduced-motion。
 * 模型经模块级缓存，卸载时仅从场景移除并不销毁其几何体/材质，供再次进入即时复用。
 */
export default function TokyoDiorama() {
    const { t } = useTranslation()
    const hostRef = useRef(null)
    const [status, setStatus] = useState('loading') // loading | ready | error

    useThreeScene(
        hostRef,
        ({ THREE, scene, camera, renderer, reduced }) => {
            renderer.toneMapping = THREE.ACESFilmicToneMapping
            renderer.toneMappingExposure = 1

            camera.fov = 40
            camera.near = 1
            camera.far = 100
            camera.position.set(6, 2.4, 9)
            camera.updateProjectionMatrix()

            // 影棚环境光（无需可见天空，模型在深色背景中如悬浮发光的立体透视盒）
            const pmrem = new THREE.PMREMGenerator(renderer)
            const envRT = pmrem.fromScene(new RoomEnvironment(), 0.04)
            scene.environment = envRT.texture
            const ambient = new THREE.AmbientLight(0xffffff, 0.35)
            const key = new THREE.DirectionalLight(0xffffff, 1.1)
            key.position.set(5, 8, 6)
            scene.add(ambient, key)

            // 交互控制：仅环视 + 缓速自转（不缩放/不平移，避免抢占页面滚动）
            const controls = new OrbitControls(camera, renderer.domElement)
            controls.enableDamping = !reduced
            controls.dampingFactor = 0.08
            controls.enableZoom = false
            controls.enablePan = false
            controls.autoRotate = !reduced
            controls.autoRotateSpeed = 0.5
            controls.minPolarAngle = 0.6
            controls.maxPolarAngle = Math.PI / 1.95
            controls.target.set(0, 0.7, 0)
            controls.update()
            const onChange = () => renderer.render(scene, camera)
            controls.addEventListener('change', onChange)

            // 加载（复用模块级缓存的解码结果）
            let cancelled = false
            let model = null
            let mixer = null
            loadTokyoModel()
                .then((gltf) => {
                    if (cancelled) return
                    model = gltf.scene
                    model.position.set(1, 1, 0)
                    model.scale.setScalar(0.01)
                    scene.add(model)
                    mixer = new THREE.AnimationMixer(model)
                    if (gltf.animations[0]) mixer.clipAction(gltf.animations[0]).reset().play()
                    if (reduced) mixer.update(2.5) // 减少动画：定格在一个生动的姿态
                    setStatus('ready')
                    renderer.render(scene, camera)
                })
                .catch((err) => {
                    if (cancelled) return
                    console.error('[TokyoDiorama] 模型加载失败', err)
                    setStatus('error')
                })

            return {
                update(_t, dt) {
                    if (mixer && !reduced) mixer.update(dt)
                    controls.update()
                },
                dispose() {
                    cancelled = true
                    controls.removeEventListener('change', onChange)
                    controls.dispose()
                    pmrem.dispose()
                    envRT.dispose?.()
                    scene.environment = null
                    if (mixer) {
                        mixer.stopAllAction()
                        if (model) mixer.uncacheRoot(model)
                    }
                    // 模型为模块级缓存资源：仅从场景移除，不销毁几何体/材质/贴图
                    if (model) scene.remove(model)
                },
            }
        },
        [],
        { fov: 40, cameraZ: 9 },
    )

    return (
        <div className="relative h-[62vh] min-h-[440px] w-full overflow-hidden rounded-3xl border border-white/10 bg-white/[0.02] md:h-[72vh]">
            {/* 中心柔光，让彩色模型在深色面板中更聚焦 */}
            <div
                className="pointer-events-none absolute inset-0"
                style={{ background: 'radial-gradient(circle at 50% 42%, rgba(255,255,255,0.10), transparent 62%)' }}
            />
            {/* WebGL 画布挂载点 */}
            <div ref={hostRef} className="absolute inset-0" />

            {/* 加载 / 出错状态 */}
            {status !== 'ready' && (
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                    <span className="text-sm text-white/50">
                        {status === 'error' ? t('common.error') : t('common.loading')}
                    </span>
                </div>
            )}

            {/* 交互提示 */}
            {status === 'ready' && (
                <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full border border-white/10 bg-black/40 px-4 py-1.5 text-xs text-white/60 backdrop-blur">
                    {t('pages.vision.showcase.hint')}
                </div>
            )}
        </div>
    )
}
