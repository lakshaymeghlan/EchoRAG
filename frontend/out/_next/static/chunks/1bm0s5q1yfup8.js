(globalThis.TURBOPACK||(globalThis.TURBOPACK=[])).push(["object"==typeof document?document.currentScript:void 0,31713,e=>{"use strict";var t=e.i(43476),s=e.i(71645);let a=`attribute vec2 a_position;
void main() {
  gl_Position = vec4(a_position, 0.0, 1.0);
}`,r=`#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif

uniform vec3 u_colors[8];
// Seven packed vectors + eight colour vectors = 15 fragment uniform vectors,
// one below WebGL1's guaranteed minimum. Macros preserve the public u_* API.
uniform vec4 u_scene;      // resolution.xy, time, colour count
uniform vec4 u_shape;      // scale, intensity, paramA, warp
uniform vec4 u_surface;    // detail, contrast, brightness, saturation
uniform vec4 u_finish;     // hue, vignette, blur, grain
uniform vec4 u_transform;  // seed, rotation, drift, OKLab toggle
uniform vec4 u_space;      // offset.xy, pointer.xy
uniform vec4 u_cursor;

#define u_resolution u_scene.xy
#define u_time u_scene.z
#define u_colorCount u_scene.w
#define u_scale u_shape.x
#define u_intensity u_shape.y
#define u_paramA u_shape.z
#define u_warp u_shape.w
#define u_detail u_surface.x
#define u_contrast u_surface.y
#define u_brightness u_surface.z
#define u_saturation u_surface.w
#define u_hue u_finish.x
#define u_vignette u_finish.y
#define u_blur u_finish.z
#define u_grain u_finish.w
#ifdef GL_FRAGMENT_PRECISION_HIGH
#define u_seed u_transform.x
#else
// Keep hash inputs inside mediump's guaranteed \xb12^14 range.
#define u_seed mod(u_transform.x, 31.0)
#endif
#define u_rotate u_transform.y
#define u_drift u_transform.z
#define u_oklab u_transform.w
#define u_offset u_space.xy
#define u_mouse u_space.zw
#define u_cursorPresence u_cursor.x
#define u_cursorEffect u_cursor.y
#define u_cursorStrength u_cursor.z
#define u_cursorRadius u_cursor.w

float hash21(vec2 p) {
#ifndef GL_FRAGMENT_PRECISION_HIGH
  p = mod(p, 31.0);
#endif
  p = fract(p * vec2(234.34, 435.345));
  p += dot(p, p + 34.23);
  return fract(p.x * p.y);
}

// Even, un-structured white noise for film grain (Dave Hoskins hash12). The
// multiply hash above is fine for value noise but shows a faint axis-aligned
// mesh at integer fragment coords, which reads as a net over flat areas.
float grainHash(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}

vec2 hash22(vec2 p) {
#ifndef GL_FRAGMENT_PRECISION_HIGH
  p = mod(p, 31.0);
#endif
  float n = sin(dot(p, vec2(41.0, 289.0)));
  return fract(vec2(15731.743, 7892.321) * n);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(
    mix(hash21(i), hash21(i + vec2(1.0, 0.0)), u.x),
    mix(hash21(i + vec2(0.0, 1.0)), hash21(i + vec2(1.0, 1.0)), u.x),
    u.y);
}

float fbm(vec2 p) {
  float v = 0.0;
  float a = 0.5;
  for (int i = 0; i < 5; i++) {
    v += a * noise(p);
    p = p * 2.03 + vec2(17.0, 9.2);
    a *= 0.5;
  }
  return v;
}

// --- OKLab colour mixing (perceptual), gated by u_oklab -----------------------
vec3 srgbToLinear(vec3 c) {
  return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)),
    step(0.04045, c));
}
vec3 linearToSrgb(vec3 c) {
  // max() guards the sRGB branch: out-of-gamut OKLab interpolations can send a
  // channel negative, and pow(negative, …) is NaN which mix()/step() would
  // then propagate. The linear branch clips such channels to 0 downstream.
  return mix(c * 12.92, 1.055 * pow(max(c, vec3(0.0)), vec3(1.0 / 2.4)) - 0.055,
    step(0.0031308, c));
}
vec3 linToOklab(vec3 c) {
  float l = 0.4122214708 * c.r + 0.5363325363 * c.g + 0.0514459929 * c.b;
  float m = 0.2119034982 * c.r + 0.6806995451 * c.g + 0.1073969566 * c.b;
  float s = 0.0883024619 * c.r + 0.2817188376 * c.g + 0.6299787005 * c.b;
  l = pow(max(l, 0.0), 1.0 / 3.0);
  m = pow(max(m, 0.0), 1.0 / 3.0);
  s = pow(max(s, 0.0), 1.0 / 3.0);
  return vec3(
    0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s);
}
vec3 oklabToLin(vec3 c) {
  float l = c.x + 0.3963377774 * c.y + 0.2158037573 * c.z;
  float m = c.x - 0.1055613458 * c.y - 0.0638541728 * c.z;
  float s = c.x - 0.0894841775 * c.y - 1.2914855480 * c.z;
  l = l * l * l; m = m * m * m; s = s * s * s;
  return vec3(
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s);
}
vec3 mixColour(vec3 a, vec3 b, float t) {
  if (u_oklab > 0.5) {
    vec3 la = linToOklab(srgbToLinear(a));
    vec3 lb = linToOklab(srgbToLinear(b));
    return clamp(linearToSrgb(oklabToLin(mix(la, lb, t))), 0.0, 1.0);
  }
  return mix(a, b, t);
}

// Mix through the recipe colours; x is clamped to 0..1. WebGL1 forbids
// dynamic uniform indexing in fragment shaders, hence the constant loop.
vec3 palette(float x) {
  float n = max(u_colorCount - 1.0, 1.0);
  float f = clamp(x, 0.0, 1.0) * n;
  vec3 col = u_colors[0];
  for (int i = 0; i < 7; i++) {
    if (float(i) < n)
      col = mixColour(col, u_colors[i + 1],
        smoothstep(0.0, 1.0, clamp(f - float(i), 0.0, 1.0)));
  }
  return col;
}

vec3 hueRotate(vec3 col, float a) {
  const mat3 toYIQ = mat3(0.299, 0.596, 0.211,
                          0.587, -0.274, -0.523,
                          0.114, -0.322, 0.312);
  const mat3 toRGB = mat3(1.0, 1.0, 1.0,
                          0.956, -0.272, -1.106,
                          0.621, -0.647, 1.703);
  vec3 yiq = toYIQ * col;
  float ca = cos(a), sa = sin(a);
  yiq = vec3(yiq.x, yiq.y * ca - yiq.z * sa, yiq.y * sa + yiq.z * ca);
  return toRGB * yiq;
}

vec3 shade(vec2 uv, vec2 p, float t) {
  float y = uv.y
    + sin(uv.x * (3.0 + u_intensity * 9.0) + t * 0.8) * 0.08
    + (fbm(p * 2.0 + t * 0.1) - 0.5) * u_intensity * 0.6;
  return palette(y);
}

void main() {
  vec2 uv = gl_FragCoord.xy / u_resolution.xy;
  vec2 screenUv = uv;
  vec2 p = (gl_FragCoord.xy - 0.5 * u_resolution.xy)
    / min(u_resolution.x, u_resolution.y);
  float cursorMask = 0.0;

  // Cursor modes 1–3 are local distortions. Push shifts the same screen-space
  // coordinates before field transforms, so Zoom/Rotate don't change its feel.
  if (u_cursorPresence > 0.001) {
    // u_mouse is normalized to -1..1 in canvas space. Convert it to the same
    // aspect-corrected screen space as p so effects stay under the cursor.
    vec2 cursor = (0.5 * u_mouse * u_resolution.xy)
      / min(u_resolution.x, u_resolution.y);
    vec2 cursorDelta = p - cursor;
    if (u_cursorEffect < 0.5) {
      p += cursor * u_cursorPresence * u_cursorStrength * 0.55;
    } else {
      float cursorDistance = length(cursorDelta);
      vec2 cursorDirection = cursorDelta / max(cursorDistance, 0.0001);
      cursorMask = u_cursorPresence
        * (1.0 - smoothstep(0.0, u_cursorRadius, cursorDistance));
      if (u_cursorEffect < 1.5) {
        p -= cursorDirection * cursorMask * u_cursorStrength * 0.24;
      } else if (u_cursorEffect < 2.5) {
        float cursorAngle = cursorMask * u_cursorStrength * 2.2;
        float cc = cos(cursorAngle), cs = sin(cursorAngle);
        p = cursor + mat2(cc, -cs, cs, cc) * cursorDelta;
      } else if (u_cursorEffect < 3.5) {
        float ripple = sin(
          cursorDistance / max(u_cursorRadius, 0.001) * 18.0 - u_time * 5.0);
        p -= cursorDirection * ripple * cursorMask * u_cursorStrength * 0.07;
      }
    }
  }

  // Keep presets that read uv (rather than p) in the same warped space.
  uv = p * min(u_resolution.x, u_resolution.y) / u_resolution.xy + 0.5;
  p *= u_scale;
  // Field transform: rotate, pan, pointer push, slow drift.
  if (abs(u_rotate) > 0.0001) {
    float cr = cos(u_rotate), sr = sin(u_rotate);
    p = mat2(cr, -sr, sr, cr) * p;
  }
  p += u_offset;
  if (u_drift > 0.0001)
    p += u_drift * vec2(sin(u_time * 0.31), cos(u_time * 0.23));
  // Organic domain warp.
  if (u_warp > 0.0) {
    p += u_warp * (vec2(
      fbm(p * u_detail + u_seed),
      fbm(p * u_detail + vec2(5.2, 1.3))) - 0.5);
  }
  // Shade, with an optional soft 5-tap blur.
  vec3 col;
  if (u_blur > 0.0) {
    float e = u_blur;
    float pe = e * u_scale;
    vec2 uvE = vec2(e) * min(u_resolution.x, u_resolution.y) / u_resolution.xy;
    col  = shade(uv, p, u_time) * 0.36;
    col += shade(uv + vec2(uvE.x, 0.0), p + vec2(pe, 0.0), u_time) * 0.16;
    col += shade(uv - vec2(uvE.x, 0.0), p - vec2(pe, 0.0), u_time) * 0.16;
    col += shade(uv + vec2(0.0, uvE.y), p + vec2(0.0, pe), u_time) * 0.16;
    col += shade(uv - vec2(0.0, uvE.y), p - vec2(0.0, pe), u_time) * 0.16;
  } else {
    col = shade(uv, p, u_time);
  }
  // Post: contrast, saturation, hue, brightness, vignette, grain.
  if (abs(u_contrast - 1.0) > 0.0001)
    col = (col - 0.5) * u_contrast + 0.5;
  if (abs(u_saturation - 1.0) > 0.0001) {
    float luma = dot(col, vec3(0.299, 0.587, 0.114));
    col = mix(vec3(luma), col, u_saturation);
  }
  if (abs(u_hue) > 0.0001)
    col = hueRotate(col, u_hue);
  if (abs(u_brightness) > 0.0001)
    col += u_brightness;
  if (u_vignette > 0.0001) {
    float vd = length(screenUv - 0.5) * 1.41421356;
    col *= 1.0 - u_vignette * smoothstep(0.35, 1.0, vd);
  }
  if (u_cursorPresence > 0.001 && u_cursorEffect > 3.5)
    col += (vec3(0.18) + col * 0.12) * cursorMask * u_cursorStrength;
  if (u_grain > 0.0001)
    col += (grainHash(
      gl_FragCoord.xy + vec2(u_seed * 17.0, u_seed * 31.0)) - 0.5) * u_grain;
  gl_FragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}
`,n=[[0,.07058823529411765,.09803921568627451],[0,.37254901960784315,.45098039215686275],[.5803921568627451,.8235294117647058,.7411764705882353],[.9137254901960784,.8470588235294118,.6509803921568628],[.9137254901960784,.8470588235294118,.6509803921568628],[.9137254901960784,.8470588235294118,.6509803921568628],[.9137254901960784,.8470588235294118,.6509803921568628],[.9137254901960784,.8470588235294118,.6509803921568628]],i=new WeakMap;function o({className:e}){let c=(0,s.useRef)(null);return(0,s.useEffect)(()=>{let e=c.current;if(!e)return;let t=i.get(e);void 0!==t&&window.clearTimeout(t),i.delete(e);let s=e.getContext("webgl",{antialias:!1});if(!s)return;let o=(e,t)=>{let a=s.createShader(e);return s.shaderSource(a,t),s.compileShader(a),a},l=s.createProgram(),u=o(s.VERTEX_SHADER,a),d=o(s.FRAGMENT_SHADER,r);s.attachShader(l,u),s.attachShader(l,d),s.linkProgram(l),s.deleteShader(u),s.deleteShader(d),s.useProgram(l);let m=s.createBuffer();s.bindBuffer(s.ARRAY_BUFFER,m),s.bufferData(s.ARRAY_BUFFER,new Float32Array([-1,-1,3,-1,-1,3]),s.STATIC_DRAW);let f=s.getAttribLocation(l,"a_position");s.enableVertexAttribArray(f),s.vertexAttribPointer(f,2,s.FLOAT,!1,0,0);let p={colors:s.getUniformLocation(l,"u_colors"),scene:s.getUniformLocation(l,"u_scene"),shape:s.getUniformLocation(l,"u_shape"),surface:s.getUniformLocation(l,"u_surface"),finish:s.getUniformLocation(l,"u_finish"),transform:s.getUniformLocation(l,"u_transform"),space:s.getUniformLocation(l,"u_space"),cursor:s.getUniformLocation(l,"u_cursor")};s.uniform3fv(p.colors,new Float32Array(n.flat())),s.uniform4f(p.shape,1.92,.6,.33,.258),s.uniform4f(p.surface,3.392,1.149,0,1),s.uniform4f(p.finish,0,.2,.0016,.07),s.uniform4f(p.transform,8231,4.1888,.148,0),s.uniform4f(p.cursor,0,2,.65,.46);let h=0,x=0,v=0,g=0,b=0,_=0,y=!1,w=0,N=0,k=e.getBoundingClientRect(),j=0,R=null,E="visible"===document.visibilityState,A=!0,M=!1,S=performance.now(),T=Math.abs(1.24)>1e-4,C=()=>{let t=Math.min(window.devicePixelRatio||1,2),a=Math.max(1,Math.round(k.width*t)),r=Math.max(1,Math.round(k.height*t)),n=Math.min(1,Math.sqrt(2e6/Math.max(1,a*r))),i=Math.max(1,Math.round(a*n)),o=Math.max(1,Math.round(r*n));(e.width!==i||e.height!==o)&&(e.width=i,e.height=o,s.viewport(0,0,i,o))};function L(){!M&&E&&A&&0===j&&(j=requestAnimationFrame(I))}let F=()=>{if(!y||0===k.width||0===k.height)return;if(!(w>=k.left&&w<=k.right&&N>=k.top&&N<=k.bottom)){v=0,L();return}let e=(w-k.left)/k.width*2-1,t=-((N-k.top)/k.height*2-1);0===v&&_<.01&&(g=e,b=t),h=e,x=t,v=1,L()},z=()=>{k=e.getBoundingClientRect(),C(),F(),L()};window.addEventListener("resize",z);let P=new ResizeObserver(z);P.observe(e);let D=new IntersectionObserver(([e])=>{(A=e?.isIntersecting??!0)?L():0!==j&&(cancelAnimationFrame(j),j=0,R=null)});D.observe(e);let G=()=>{(E="visible"===document.visibilityState)?L():0!==j&&(cancelAnimationFrame(j),j=0,R=null)};function I(t){if(j=0,M||!E||!A)return;let a=null===R?0:Math.min((t-R)/1e3,.1);R=t;let r=1-Math.exp(-12*a);g+=(h-g)*r,b+=(x-b)*r,_+=(v-_)*r,C();let n=e.width,i=e.height;s.uniform4f(p.scene,n,i,(t-S)/1e3*1.24,4),s.uniform4f(p.space,-.05,-.13,g,b),s.uniform4f(p.cursor,0,2,.65,.46),s.drawArrays(s.TRIANGLES,0,3);let o=Math.abs(h-g)>.001||Math.abs(x-b)>.001||Math.abs(v-_)>.001;T||o?L():R=null}return document.addEventListener("visibilitychange",G),L(),()=>{M=!0,cancelAnimationFrame(j),P.disconnect(),D.disconnect(),document.removeEventListener("visibilitychange",G),window.removeEventListener("resize",z),s.deleteBuffer(m),s.deleteProgram(l);let t=window.setTimeout(()=>{i.get(e)===t&&(i.delete(e),s.getExtension("WEBGL_lose_context")?.loseContext(),e.width=1,e.height=1)},0);i.set(e,t)}},[]),(0,t.jsx)("canvas",{ref:c,className:e,style:{display:"block",width:"100%",height:"100%"}})}async function c(e,t){let s=await fetch(`https://placeholder.onrender.com${e}`,{method:"POST",body:t});if(!s.ok)throw Error(await s.text().catch(()=>"")||`${s.status} ${s.statusText}`);return s.json()}function l(){let e=window;return e.SpeechRecognition??e.webkitSpeechRecognition}let u=[{label:"what is a corporation?",hint:"English"},{label:"कॉर्पोरेशन क्या है?",hint:"Hindi"},{label:"who invented the telephone",hint:"entity"},{label:"what is my bank account balance",hint:"refused"}],d=[{key:"embed",color:"var(--color-sand)",label:"embed"},{key:"retrieve",color:"var(--color-mint)",label:"retrieve"},{key:"extract",color:"var(--color-deep)",label:"answer"}];function m({spans:e,budget:s}){let a=e.total??0,r=a<=s;return(0,t.jsxs)("div",{className:"flex flex-col gap-3",children:[(0,t.jsxs)("div",{className:"flex items-baseline justify-between gap-4",children:[(0,t.jsx)("span",{className:"font-mono text-[11px] uppercase tracking-[0.18em] text-sand/45",children:"pipeline latency"}),(0,t.jsxs)("span",{className:"font-mono text-xs tabular-nums text-sand/45",children:["budget ",s.toFixed(0),"ms"]})]}),(0,t.jsx)("div",{className:"flex h-2 w-full overflow-hidden rounded-full bg-abyss/60 ring-1 ring-inset ring-white/10",role:"img","aria-label":`${a.toFixed(0)} milliseconds of a ${s} millisecond budget`,children:d.map(({key:a,color:r})=>{let n=e[a];return n?(0,t.jsx)("div",{className:"h-full transition-[width] duration-500 ease-out",style:{width:`${Math.min(n/s*100,100)}%`,background:r}},a):null})}),(0,t.jsxs)("div",{className:"flex flex-wrap items-center gap-x-5 gap-y-2",children:[d.map(({key:s,color:a,label:r})=>void 0===e[s]?null:(0,t.jsxs)("span",{className:"flex items-center gap-2 font-mono text-xs text-sand/60",children:[(0,t.jsx)("span",{className:"size-2 rounded-full",style:{background:a},"aria-hidden":!0}),r,(0,t.jsxs)("span",{className:"tabular-nums text-sand/90",children:[e[s].toFixed(1),"ms"]})]},s)),(0,t.jsxs)("span",{className:`ml-auto font-mono text-xs tabular-nums ${r?"text-mint":"text-clay"}`,children:[a.toFixed(1),"ms ",r?"· within budget":"· over budget"]})]})]})}e.s(["default",0,function(){let[e,a]=(0,s.useState)(null),[r,n]=(0,s.useState)(!1),[i,d]=(0,s.useState)(null),[f,p]=(0,s.useState)(""),h=(0,s.useCallback)(async e=>{n(!0),d(null);try{a(await e())}catch(e){d(e instanceof Error?e.message:"Request failed")}finally{n(!1)}},[]),{recording:x,error:v,start:g,stop:b}=function(e,t=25e3){let[a,r]=(0,s.useState)(!1),[n,i]=(0,s.useState)(null),o=(0,s.useRef)(null),c=(0,s.useRef)(null),l=(0,s.useCallback)(()=>{c.current&&clearTimeout(c.current),o.current?.stop(),o.current?.stream.getTracks().forEach(e=>e.stop()),r(!1)},[]);return{recording:a,error:n,start:(0,s.useCallback)(async()=>{i(null);try{let s=await navigator.mediaDevices.getUserMedia({audio:!0}),a=[],n=new MediaRecorder(s);n.ondataavailable=e=>e.data.size>0&&a.push(e.data),n.onstop=()=>e(new Blob(a,{type:n.mimeType})),o.current=n,n.start(),r(!0),c.current=setTimeout(l,t)}catch{i("Microphone blocked. Allow access, or type your question instead.")}},[e,t,l]),stop:l}}((0,s.useCallback)(e=>h(()=>{let t;return(t=new FormData).append("audio",e,"query.webm"),c("/ask-voice",t)}),[h])),_=(0,s.useRef)(b);_.current=b;let y=function(e){let[t,a]=(0,s.useState)(""),r=(0,s.useRef)(null),n=(0,s.useRef)(e);n.current=e;let i=(0,s.useCallback)(()=>{a("");let e=l();if(!e)return!1;let t=new e;t.lang="en-IN",t.continuous=!0,t.interimResults=!0,t.onresult=e=>{let t="";for(let s=0;s<e.results.length;s++)t+=e.results[s][0].transcript;a(t.trim())},t.onend=()=>n.current?.(),t.onerror=()=>{};try{return t.start(),r.current=t,!0}catch{return!1}},[]);return{caption:t,setCaption:a,start:i,stop:(0,s.useCallback)(()=>{let e=r.current;if(r.current=null,e){e.onend=null;try{e.stop()}catch{}}},[])}}(()=>_.current()),w=e=>{e.trim()&&!r&&(p(e),h(()=>{let t;return(t=new FormData).append("text",e),c("/ask",t)}))},N=x?y.caption:f,k=e?.type==="abstention";return(0,t.jsxs)("div",{className:"relative min-h-screen w-full overflow-hidden bg-abyss",children:[(0,t.jsx)(o,{className:"pointer-events-none absolute inset-0"}),(0,t.jsx)("div",{className:"pointer-events-none absolute inset-0 bg-gradient-to-b from-abyss/85 via-abyss/60 to-abyss/90","aria-hidden":!0}),(0,t.jsxs)("main",{className:"relative mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-10 px-6 py-16 sm:px-10",children:[(0,t.jsxs)("header",{className:"flex flex-col gap-3",children:[(0,t.jsxs)("div",{className:"flex items-center gap-3",children:[(0,t.jsx)("span",{className:"size-1.5 rounded-full bg-mint","aria-hidden":!0}),(0,t.jsx)("span",{className:"font-mono text-[11px] uppercase tracking-[0.22em] text-mint/70",children:"voice rag · msmarco-xi"})]}),(0,t.jsxs)("h1",{className:"font-display text-6xl leading-[0.95] tracking-tight text-sand sm:text-7xl",children:["Echo",(0,t.jsx)("span",{className:"italic text-mint",children:"RAG"})]}),(0,t.jsxs)("p",{className:"max-w-xl text-[15px] leading-relaxed text-sand/60",children:["Ask in Hindi or English. Every answer is a verbatim span of a retrieved passage — or an honest refusal."," ",(0,t.jsx)("span",{className:"text-sand/40",children:"Retrieval to answer in under 200 milliseconds."})]})]}),(0,t.jsxs)("section",{className:"flex flex-col gap-4",children:[(0,t.jsxs)("div",{className:"flex items-center gap-3 rounded-2xl border border-white/10 bg-abyss/40 p-2 backdrop-blur-xl transition focus-within:border-mint/40",children:[(0,t.jsx)("button",{onClick:x?()=>{y.stop(),b()}:()=>{p(""),y.start(),g()},disabled:r&&!x,"aria-label":x?"Stop recording":"Record a question",className:`grid size-11 shrink-0 place-items-center rounded-xl transition disabled:opacity-40 ${x?"pulse-ring bg-mint text-abyss":"bg-sand/10 text-sand hover:bg-sand/20"}`,children:x?(0,t.jsx)("span",{className:"size-3 rounded-[3px] bg-abyss","aria-hidden":!0}):(0,t.jsxs)("svg",{viewBox:"0 0 24 24",className:"size-5",fill:"none","aria-hidden":!0,children:[(0,t.jsx)("path",{d:"M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Z",stroke:"currentColor",strokeWidth:"1.6"}),(0,t.jsx)("path",{d:"M19 11a7 7 0 0 1-14 0M12 18v3",stroke:"currentColor",strokeWidth:"1.6",strokeLinecap:"round"})]})}),(0,t.jsxs)("div",{className:"relative min-w-0 flex-1",children:[(0,t.jsx)("input",{value:N,onChange:e=>p(e.target.value),onKeyDown:e=>"Enter"===e.key&&w(f),readOnly:x,placeholder:x?l()?"Listening…":"Recording… press stop when done":"Ask a question, or press record","aria-label":"Question",className:`w-full bg-transparent px-1 text-[15px] outline-none placeholder:text-sand/30 ${x?"text-mint":"text-sand"}`}),x&&(0,t.jsx)("span",{className:"absolute -top-5 left-1 font-mono text-[10px] uppercase tracking-[0.16em] text-mint/50","aria-hidden":!0,children:"live caption · sarvam transcribes on stop"})]}),(0,t.jsx)("button",{onClick:()=>w(f),disabled:r||x||!f.trim(),className:"shrink-0 rounded-xl bg-mint px-5 py-2.5 font-mono text-xs uppercase tracking-widest text-abyss transition hover:bg-sand disabled:opacity-25",children:"Ask"})]}),(0,t.jsx)("div",{className:"flex flex-wrap gap-2",children:u.map(({label:e,hint:s})=>(0,t.jsxs)("button",{onClick:()=>w(e),disabled:r,className:"group flex items-center gap-2 rounded-full border border-white/10 px-3 py-1.5 text-[13px] text-sand/60 transition hover:border-mint/40 hover:text-sand disabled:opacity-30",children:[e,(0,t.jsx)("span",{className:"font-mono text-[10px] uppercase tracking-wider text-sand/25 group-hover:text-mint/60",children:s})]},e))})]}),(0,t.jsxs)("section",{className:"min-h-[13rem]","aria-live":"polite",children:[v&&(0,t.jsx)("p",{className:"text-sm text-clay",children:v}),i&&(0,t.jsxs)("p",{className:"font-mono text-sm text-clay",children:[i," — is the API running on :8000?"]}),r&&(0,t.jsxs)("div",{className:"flex items-center gap-3 font-mono text-xs uppercase tracking-[0.2em] text-sand/40",children:[(0,t.jsx)("span",{className:"size-1.5 animate-pulse rounded-full bg-mint","aria-hidden":!0}),"working"]}),e&&!r&&(0,t.jsxs)("article",{className:"rise flex flex-col gap-6 rounded-2xl border border-white/10 bg-abyss/45 p-6 backdrop-blur-xl sm:p-8",children:[(0,t.jsxs)("div",{className:"flex flex-wrap items-center gap-3",children:[(0,t.jsx)("span",{className:`font-mono text-[11px] uppercase tracking-[0.18em] ${k?"text-clay":"text-mint"}`,children:k?`declined \xb7 ${e.reason}`:"answer"}),void 0!==e.confidence&&(0,t.jsxs)("span",{className:"font-mono text-[11px] tabular-nums text-sand/35",children:["confidence ",e.confidence.toFixed(3)]}),e.citations?.length?(0,t.jsxs)("span",{className:"font-mono text-[11px] text-sand/35",children:["passage ",e.citations.join(", ")]}):null]}),(0,t.jsx)("p",{className:`font-display text-2xl leading-snug sm:text-[28px] ${k?"text-sand/70":"text-sand"}`,children:e.text}),e.transcript&&(0,t.jsxs)("p",{className:"border-l-2 border-mint/25 pl-4 text-sm text-sand/45",children:["heard ",(0,t.jsx)("span",{className:"italic text-sand/70",children:e.transcript}),null!=e.stt_ms&&(0,t.jsxs)("span",{className:"ml-2 font-mono text-xs tabular-nums text-sand/30",children:["speech-to-text ",e.stt_ms.toFixed(0),"ms · measured, outside the budget"]})]}),(0,t.jsx)("div",{className:"border-t border-white/10 pt-5",children:(0,t.jsx)(m,{spans:e.spans,budget:e.slo_ms})})]})]}),(0,t.jsxs)("footer",{className:"font-mono text-[11px] leading-relaxed text-sand/25",children:["99,985 passages · multilingual-e5-small · LanceDB hybrid retrieval · RRF fusion",(0,t.jsx)("br",{}),"answers extracted, never generated — nothing to hallucinate"]})]})]})}],31713)}]);