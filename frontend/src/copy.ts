/**
 * 클라이언트 전용 문안 (구현명세서 §2.10 · §4.0).
 *
 * **원칙: 화면 문안은 서버가 내려준다**(`backend/app/assets/screen_copy.py`). 명세서 §4의
 * [정본]·[제안] 문안이 자산 계약 테스트로 명세서와 대조되려면 한 곳에 있어야 하기 때문이다.
 *
 * 여기 남는 것은 두 종류뿐이다.
 * ① 세션이 없을 때(P0·데스크톱 가드) 필요한 문안 — 서버에 물어볼 쿠키가 없다.
 * ② 명세서가 문안을 주지 않은 **이동 버튼 라벨**. 연구 문안이 아니라 UI 라벨이다.
 *    `<TODO: PI 확인 — 명세서 §4에 라벨을 명시할지 결정>`
 */

/** §2.10·§4.0 데스크톱 가드 — 서버 `screen_copy.DESKTOP_ONLY`와 같은 문장이다. */
export const DESKTOP_ONLY = '이 연구는 데스크톱(노트북) 브라우저에서만 진행할 수 있습니다.'
export const MIN_VIEWPORT_WIDTH = 1024

/** §4.0 P0 입력 라벨 */
export const JOIN_TITLE = '연구 참여'
export const JOIN_PARTICIPANT_LABEL = '참가자 번호'
export const JOIN_CODE_LABEL = '접속 코드'
export const JOIN_SUBMIT = '시작하기'

/** §9.1 — 서버가 이유를 주지 않을 때의 기본 문안 */
export const SAVE_FAILED = '저장을 완료하지 못했습니다. 다시 시도해주세요.'
export const RESTORING = '진행 중이던 화면을 복구합니다.'

/** 이동 버튼 라벨 (명세서 미지정 — UI 라벨) */
export const NEXT = '계속하기'
/** §3.2 B0 — "시작" → B1 */
export const START = '시작'
export const SUBMIT = '제출하기'
export const DONE_NOTICE = '세션이 종료되었습니다. 연구자의 안내를 기다려주세요.'
