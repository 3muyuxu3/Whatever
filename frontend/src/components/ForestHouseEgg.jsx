import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { useThreeScene } from '../hooks/useThreeScene'

const MODEL_URL = '/models/forest_house.glb'

// 模块级缓存：整站仅解码一次 GLB（解码器走 public/draco/，dev 与生产均可用），
// 并避免 StrictMode 双挂载中止解码 worker；失败则清空缓存以便重试。
let housePromise = null
function loadForestHouse() {
    if (!housePromise) {
        housePromise = new Promise((resolve, reject) => {
            const draco = new DRACOLoader().setDecoderPath('/draco/')
            const loader = new GLTFLoader()
            loader.setDRACOLoader(draco)
            loader.load(
                MODEL_URL,
                (gltf) => { draco.dispose(); resolve(gltf) },
                undefined,
                (err) => { draco.dispose(); housePromise = null; reject(err) },
            )
        })
    }
    return housePromise
}

/**
 * ForestHouseEgg —— 首页彩蛋：森林小屋
 *
 * 在首页底部 MUYU 巨字上快速连点三次触发。全屏奶油色场景（贴合模型的手绘水彩风），
 * 展示可交互的森林小屋：拖动环视、滚轮缩放、缓速自转；Esc 或右上角按钮关闭。
 * 组件按需懒加载，模型经模块级缓存，卸载时仅从场景移除以便再次打开秒现。
 */
export default function ForestHouseEgg({ onClose }) {
    const { t } = useTranslation()
    const hostRef = useRef(null)
    const [status, setStatus] = useState('loading') // loading | ready | error

    // Esc 关闭 + 打开期间锁定页面滚动
    useEffect(() => {
        const onKey = (e) => { if (e.key === 'Escape') onClose() }
        window.addEventListener('keydown', onKey)
        const prevOverflow = document.body.style.overflow
        document.body.style.overflow = 'hidden'
        return () => {
            window.removeEventListener('keydown', onKey)
            document.body.style.overflow = prevOverflow
        }
    }, [onClose])

    useThreeScene(
        hostRef,
        ({ THREE, scene, camera, renderer, reduced }) => {
            camera.fov = 45
            camera.near = 0.1
            camera.far = 100
            camera.position.set(1.5, 4, 9)
            camera.updateProjectionMatrix()

            // 奶油色底 + 兜底环境光（模型以烘焙贴图为主）
            renderer.setClearColor(0xf6eedc, 1)
            scene.add(new THREE.AmbientLight(0xffffff, 1))

            const controls = new OrbitControls(camera, renderer.domElement)
            controls.enableDamping = !reduced
            controls.dampingFactor = 0.08
            controls.enablePan = false
            controls.minDistance = 4
            controls.maxDistance = 18
            controls.maxPolarAngle = Math.PI / 1.9
            controls.autoRotate = !reduced
            controls.autoRotateSpeed = 0.8
            controls.target.set(0, 2, 0)
            controls.update()
            const onChange = () => renderer.render(scene, camera)
            controls.addEventListener('change', onChange)

            let cancelled = false
            let model = null
            loadForestHouse()
                .then((gltf) => {
                    if (cancelled) return
                    model = gltf.scene
                    scene.add(model)
                    setStatus('ready')
                    renderer.render(scene, camera)
                })
                .catch((err) => {
                    if (cancelled) return
                    console.error('[ForestHouseEgg] 模型加载失败', err)
                    setStatus('error')
                })

            return {
                update() {
                    controls.update()
                },
                dispose() {
                    cancelled = true
                    controls.removeEventListener('change', onChange)
                    controls.dispose()
                    // 模型为模块级缓存资源：仅从场景移除，不销毁几何体/材质
                    if (model) scene.remove(model)
                },
            }
        },
        [],
        { fov: 45, cameraZ: 9 },
    )

    return (
        <div className="fixed inset-0 z-[100]" style={{ backgroundColor: '#f6eedc' }}>
            {/* WebGL 画布挂载点 */}
            <div ref={hostRef} className="absolute inset-0" />

            {/* 标题与说明 */}
            <div className="pointer-events-none absolute left-6 top-6 max-w-sm md:left-10 md:top-10">
                <h2 className="text-xl font-semibold text-neutral-800 md:text-2xl" style={{ letterSpacing: '-0.02em' }}>
                    {t('pages.egg.title')}
                </h2>
                <p className="mt-1.5 text-sm text-neutral-500">{t('pages.egg.desc')}</p>
            </div>

            {/* 关闭按钮 */}
            <button
                type="button"
                onClick={onClose}
                aria-label={t('pages.egg.close')}
                className="absolute right-6 top-6 flex h-10 w-10 items-center justify-center rounded-full border border-neutral-300 bg-white/70 text-lg leading-none text-neutral-700 backdrop-blur transition hover:bg-white md:right-10 md:top-10"
            >
                ✕
            </button>

            {/* 加载 / 出错状态 */}
            {status !== 'ready' && (
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                    <span className="text-sm text-neutral-500">
                        {status === 'error' ? t('common.error') : t('common.loading')}
                    </span>
                </div>
            )}

            {/* 交互提示 */}
            {status === 'ready' && (
                <div className="pointer-events-none absolute bottom-6 left-1/2 -translate-x-1/2 rounded-full border border-neutral-300 bg-white/70 px-4 py-1.5 text-xs text-neutral-600 backdrop-blur">
                    {t('pages.egg.hint')}
                </div>
            )}
        </div>
    )
}
