import { useRef } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useGSAP } from '@gsap/react'
import SiteHeader from '../components/SiteHeader'
import SiteFooter from '../components/SiteFooter'
import AnimatedHeading from '../components/AnimatedHeading'
import TokyoDiorama from '../components/TokyoDiorama'
import { useThreeScene } from '../hooks/useThreeScene'
import { SIMPLEX_NOISE_GLSL } from '../three/noise'

gsap.registerPlugin(useGSAP, ScrollTrigger)

/**
 * MirrorScene —— 「镜像世界」3D 背景
 * 一颗以 Simplex 噪声做顶点位移、菲涅尔描边的深色球体（象征会呼吸的镜面），
 * 外覆淡线框壳与粒子光晕，随鼠标产生轻微视差。
 */
function MirrorScene() {
    const hostRef = useRef(null)

    useThreeScene(
        hostRef,
        ({ THREE, scene, camera }) => {
            camera.position.z = 4.2
            const group = new THREE.Group()
            scene.add(group)

            const uniforms = {
                uTime: { value: 0 },
                uAmp: { value: 1 },
                uColorA: { value: new THREE.Color('#0a0a12') },
                uColorB: { value: new THREE.Color('#e8ecff') },
            }
            const mat = new THREE.ShaderMaterial({
                uniforms,
                vertexShader: /* glsl */ `
                    uniform float uTime; uniform float uAmp;
                    varying vec3 vNormal; varying vec3 vView;
                    ${SIMPLEX_NOISE_GLSL}
                    void main(){
                        float n = snoise(normal * 1.3 + uTime * 0.22);
                        float n2 = snoise(position * 2.1 - uTime * 0.13);
                        vec3 disp = position + normal * (n * 0.26 + n2 * 0.12) * uAmp;
                        vec4 mv = modelViewMatrix * vec4(disp, 1.0);
                        vNormal = normalize(normalMatrix * normal);
                        vView = normalize(-mv.xyz);
                        gl_Position = projectionMatrix * mv;
                    }
                `,
                fragmentShader: /* glsl */ `
                    uniform vec3 uColorA; uniform vec3 uColorB;
                    varying vec3 vNormal; varying vec3 vView;
                    void main(){
                        float fres = pow(1.0 - max(dot(vNormal, vView), 0.0), 2.4);
                        gl_FragColor = vec4(mix(uColorA, uColorB, fres), 1.0);
                    }
                `,
            })
            const geo = new THREE.IcosahedronGeometry(1.5, 16)
            const mesh = new THREE.Mesh(geo, mat)
            group.add(mesh)

            // 淡线框外壳
            const wireGeo = new THREE.IcosahedronGeometry(1.9, 3)
            const wireMat = new THREE.MeshBasicMaterial({
                color: 0xffffff, wireframe: true, transparent: true, opacity: 0.06,
            })
            const wire = new THREE.Mesh(wireGeo, wireMat)
            group.add(wire)

            // 粒子光晕
            const COUNT = 900
            const pos = new Float32Array(COUNT * 3)
            for (let i = 0; i < COUNT; i++) {
                const r = 2.5 + Math.random() * 2.2
                const th = Math.random() * Math.PI * 2
                const ph = Math.acos(2 * Math.random() - 1)
                pos[i * 3] = r * Math.sin(ph) * Math.cos(th)
                pos[i * 3 + 1] = r * Math.sin(ph) * Math.sin(th)
                pos[i * 3 + 2] = r * Math.cos(ph)
            }
            const pgeo = new THREE.BufferGeometry()
            pgeo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
            const pmat = new THREE.PointsMaterial({
                color: 0xffffff, size: 0.014, transparent: true, opacity: 0.5, sizeAttenuation: true,
            })
            const points = new THREE.Points(pgeo, pmat)
            scene.add(points)

            // 鼠标视差
            const target = { x: 0, y: 0 }
            const ease = { x: 0, y: 0 }
            let spin = 0
            const onMove = (e) => {
                target.x = (e.clientX / window.innerWidth) * 2 - 1
                target.y = (e.clientY / window.innerHeight) * 2 - 1
            }
            window.addEventListener('pointermove', onMove, { passive: true })

            return {
                update(t, dt) {
                    uniforms.uTime.value = t
                    spin += dt * 0.14
                    ease.x += (target.x * 0.4 - ease.x) * 0.05
                    ease.y += (target.y * 0.25 - ease.y) * 0.05
                    group.rotation.y = spin + ease.x
                    group.rotation.x = ease.y
                    points.rotation.y = t * 0.03
                    points.rotation.x = t * 0.012
                },
                dispose() {
                    window.removeEventListener('pointermove', onMove)
                    geo.dispose(); mat.dispose()
                    wireGeo.dispose(); wireMat.dispose()
                    pgeo.dispose(); pmat.dispose()
                },
            }
        },
        [],
    )

    return <div ref={hostRef} className="absolute inset-0" aria-hidden="true" />
}

/**
 * VisionView —— 「理念」页面
 * 以 3D 镜面球体为主视觉，滚动逐段揭示项目的核心理念。
 */
export default function VisionView() {
    const { t } = useTranslation()
    const rootRef = useRef(null)
    const sections = t('pages.vision.sections', { returnObjects: true }) || []

    useGSAP(() => {
        const mm = gsap.matchMedia()
        mm.add('(prefers-reduced-motion: no-preference)', () => {
            gsap.utils.toArray('.v-reveal').forEach((el) => {
                gsap.from(el, {
                    y: 48,
                    autoAlpha: 0,
                    duration: 0.9,
                    ease: 'power3.out',
                    scrollTrigger: { trigger: el, start: 'top 82%', once: true },
                })
            })
        })
        return () => mm.revert()
    }, { scope: rootRef })

    return (
        <div ref={rootRef} className="relative min-h-screen bg-black text-white">
            <SiteHeader />

            {/* ===== 3D 主视觉 ===== */}
            <section className="relative -mt-[72px] flex min-h-screen items-center overflow-hidden">
                <MirrorScene />
                <div className="relative z-10 w-full px-6 pt-[72px] md:px-10 lg:px-14">
                    <div className="mx-auto max-w-4xl text-center">
                        <p className="mb-5 text-xs font-medium uppercase tracking-[0.3em] text-white/50">
                            {t('pages.vision.kicker')}
                        </p>
                        <AnimatedHeading
                            text={t('pages.vision.title')}
                            className="text-4xl font-normal leading-tight md:text-6xl lg:text-7xl"
                            style={{ letterSpacing: '-0.03em' }}
                        />
                        <p className="mx-auto mt-6 max-w-2xl text-base text-white/70 md:text-lg">
                            {t('pages.vision.lead')}
                        </p>
                        <div className="mt-9 flex flex-wrap justify-center gap-4">
                            <Link
                                to="/#start"
                                className="rounded-lg bg-white px-8 py-3 font-medium text-black transition hover:bg-gray-100"
                            >
                                {t('pages.cta')}
                            </Link>
                            <Link
                                to="/capabilities"
                                className="liquid-glass rounded-lg border border-white/20 px-8 py-3 font-medium text-white transition hover:bg-white hover:text-black"
                            >
                                {t('pages.learnMore')}
                            </Link>
                        </div>
                    </div>
                </div>
                <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex justify-center pb-8">
                    <span className="text-xs uppercase tracking-[0.25em] text-white/40">{t('pages.scrollHint')}</span>
                </div>
                <div className="pointer-events-none absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-black to-transparent" />
            </section>

            {/* ===== 会呼吸的镜像世界（3D 动画模型展示） ===== */}
            <section className="relative mx-auto max-w-6xl px-6 py-24 md:px-10 lg:px-14">
                <div className="v-reveal mx-auto mb-10 max-w-3xl text-center">
                    <p className="mb-4 text-xs font-medium uppercase tracking-[0.3em] text-white/50">
                        {t('pages.vision.showcase.kicker')}
                    </p>
                    <h2 className="mb-4 text-3xl font-normal md:text-4xl" style={{ letterSpacing: '-0.03em' }}>
                        {t('pages.vision.showcase.title')}
                    </h2>
                    <p className="mx-auto max-w-2xl text-base text-white/65 md:text-lg">
                        {t('pages.vision.showcase.desc')}
                    </p>
                </div>
                <div className="v-reveal">
                    <TokyoDiorama />
                </div>
            </section>

            {/* ===== 理念分段 ===== */}
            <section className="relative mx-auto max-w-5xl px-6 py-28 md:px-10 lg:px-14">
                <div className="space-y-20 md:space-y-28">
                    {sections.map((s, i) => (
                        <div
                            key={i}
                            className={`v-reveal flex flex-col gap-6 md:flex-row md:items-start md:gap-12 ${i % 2 === 1 ? 'md:flex-row-reverse' : ''
                                }`}
                        >
                            <div className="shrink-0 text-6xl font-light tabular-nums text-white/15 md:text-7xl">
                                {String(i + 1).padStart(2, '0')}
                            </div>
                            <div className="md:pt-3">
                                <h2 className="mb-4 text-2xl font-medium md:text-3xl" style={{ letterSpacing: '-0.02em' }}>
                                    {s.title}
                                </h2>
                                <p className="max-w-xl text-base leading-relaxed text-white/65 md:text-lg">
                                    {s.body}
                                </p>
                            </div>
                        </div>
                    ))}
                </div>
            </section>

            {/* ===== 收束 CTA ===== */}
            <section className="v-reveal border-t border-white/10 px-6 py-24 text-center md:px-10 lg:px-14">
                <h2 className="mx-auto mb-8 max-w-3xl text-3xl font-normal md:text-5xl" style={{ letterSpacing: '-0.03em' }}>
                    {t('brand.slogan')}
                </h2>
                <Link
                    to="/#start"
                    className="inline-block rounded-lg bg-white px-8 py-3 font-medium text-black transition hover:bg-gray-100"
                >
                    {t('pages.cta')}
                </Link>
            </section>

            <SiteFooter />
        </div>
    )
}
