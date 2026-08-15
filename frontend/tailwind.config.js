/** @type {import('tailwindcss').Config} */

/*
 * 참가자 UI 색 토큰 (구 리포에서 이식 — 대비 실측값 유지).
 *
 * 파랑은 **두 가지 뜻에만** 쓴다: ① 제출 = "여기를 눌러 다음으로" ② 포커스·안내.
 * 선택 상태는 검정으로 남긴다 — 선택과 제출이 같은 색이면 "내가 고른 것"과
 * "눌러야 할 것"이 구분되지 않는다.
 *
 * 대비 실측(WCAG, 흰 배경): accent.deep 7.56:1 · accent 5.93:1 · accent.soft 1.15:1.
 * accent.soft는 **배경 전용**이다. edge는 미선택 컨트롤 테두리다.
 *
 * 다크모드는 도입하지 않는다 — 자극(AI1 카드·채팅 버블)의 표시 조건이 참가자 기기 설정에
 * 따라 갈리면 자극 동일성이 깨진다(§0.4 조작 안정성).
 *
 * ⚠ 데스크톱 전용이다(D-12·§2.10). 모바일 대응 CSS·터치 타깃 규칙은 작성하지 않는다.
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#111827',
        edge: '#9AA5B1',
        hair: '#E3E8EE',
        accent: {
          DEFAULT: '#0369A1',
          deep: '#075985',
          soft: '#E0F2FE',
        },
      },
    },
  },
  plugins: [],
}
