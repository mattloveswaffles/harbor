// Hugeicons (MIT, see assets/hugeicons-LICENSE.md) as one inline sprite; <Icon name> references a symbol.
import type { CSSProperties } from 'react';

export type IconName =
  | 'location'
  | 'arrow'
  | 'tick'
  | 'check'
  | 'car'
  | 'bus'
  | 'fuel'
  | 'hotel'
  | 'wallet'
  | 'bank'
  | 'savings'
  | 'chart'
  | 'clock'
  | 'alert'
  | 'route'
  | 'shield'
  | 'lock'
  | 'undo'
  | 'home'
  | 'rain'
  | 'traffic'
  | 'send'
  | 'link'
  | 'group'
  | 'tornado'
  | 'nav'
  | 'calendar'
  | 'plus'
  | 'close'
  | 'phone'
  | 'piggy'
  | 'wheelchair'
  | 'pin'
  | 'tent'
  | 'water'
  | 'money'
  | 'map'
  | 'zap'
  | 'heart'
  | 'plug'
  | 'logout'
  | 'play'
  | 'next'
  | 'refresh'
  | 'harbor'
  | 'settings'
  | 'pill'
  | 'user'
  | 'external'
  | 'activity'
  | 'forward'
  | 'search'
  | 'chevron'
  | 'thought';

export function Icon({ name, className, style }: { name: IconName; className?: string; style?: CSSProperties }) {
  return (
    <svg className={className ? `icon ${className}` : 'icon'} style={style} aria-hidden="true">
      <use href={`#i-${name}`} />
    </svg>
  );
}

/** Rendered once at the root. */
export function IconSprite() {
  return (
    <svg className="svg-library" aria-hidden="true">
      <symbol id="i-location" viewBox="0 0 24 24" fill="none">
        <path
          d="M13.6177 21.367C13.1841 21.773 12.6044 22 12.0011 22C11.3978 22 10.8182 21.773 10.3845 21.367C6.41302 17.626 1.09076 13.4469 3.68627 7.37966C5.08963 4.09916 8.45834 2 12.0011 2C15.5439 2 18.9126 4.09916 20.316 7.37966C22.9082 13.4393 17.599 17.6389 13.6177 21.367Z"
          stroke="currentColor"
          strokeWidth="1.5"
        />
        <path
          d="M15.5 11C15.5 12.933 13.933 14.5 12 14.5C10.067 14.5 8.5 12.933 8.5 11C8.5 9.067 10.067 7.5 12 7.5C13.933 7.5 15.5 9.067 15.5 11Z"
          stroke="currentColor"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-arrow" viewBox="0 0 24 24" fill="none">
        <path
          d="M18.5 12L4.99997 12"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M13 18C13 18 19 13.5811 19 12C19 10.4188 13 6 13 6"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-tick" viewBox="0 0 24 24" fill="none">
        <path
          d="M5 14L8.5 17.5L19 6.5"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-check" viewBox="0 0 24 24" fill="none">
        <path
          d="M22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22C17.5228 22 22 17.5228 22 12Z"
          stroke="currentColor"
          strokeWidth="1.5"
        />
        <path
          d="M8 12.5L10.5 15L16 9"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-car" viewBox="0 0 24 24" fill="none">
        <path d="M2.5 12L4.5 13" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
        <path
          d="M21.5 12.5L19.5 13"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M8 17.5L8.24567 16.8858C8.61101 15.9725 8.79368 15.5158 9.17461 15.2579C9.55553 15 10.0474 15 11.0311 15H12.9689C13.9526 15 14.4445 15 14.8254 15.2579C15.2063 15.5158 15.389 15.9725 15.7543 16.8858L16 17.5"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M2 17V19.882C2 20.2607 2.24075 20.607 2.62188 20.7764C2.86918 20.8863 3.10538 21 3.39058 21H5.10942C5.39462 21 5.63082 20.8863 5.87812 20.7764C6.25925 20.607 6.5 20.2607 6.5 19.882V18"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M17.5 18V19.882C17.5 20.2607 17.7408 20.607 18.1219 20.7764C18.3692 20.8863 18.6054 21 18.8906 21H20.6094C20.8946 21 21.1308 20.8863 21.3781 20.7764C21.7592 20.607 22 20.2607 22 19.882V17"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path d="M20 8.5L21 8" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
        <path d="M4 8.5L3 8" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
        <path
          d="M4.5 9L5.5883 5.73509C6.02832 4.41505 6.24832 3.75503 6.7721 3.37752C7.29587 3 7.99159 3 9.38304 3H14.617C16.0084 3 16.7041 3 17.2279 3.37752C17.7517 3.75503 17.9717 4.41505 18.4117 5.73509L19.5 9"
          stroke="currentColor"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M4.5 9H19.5C20.4572 10.0135 22 11.4249 22 12.9996V16.4702C22 17.0407 21.6205 17.5208 21.1168 17.5875L18 18H6L2.88316 17.5875C2.37955 17.5208 2 17.0407 2 16.4702V12.9996C2 11.4249 3.54279 10.0135 4.5 9Z"
          stroke="currentColor"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-bus" viewBox="0 0 24 24" fill="none">
        <path d="M17 20.5V22" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
        <path d="M7 20.5V22" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
        <path
          d="M4 6.78186C4 6.14251 4 5.82283 4.17387 5.43355C4.34773 5.04428 4.52427 4.88606 4.87736 4.56964C6.03437 3.53277 8.36029 2 12 2C15.6397 2 17.9656 3.53277 19.1226 4.56964C19.4757 4.88606 19.6523 5.04428 19.8261 5.43355C20 5.82283 20 6.14251 20 6.78186V14C20 16.8284 20 18.2426 19.1213 19.1213C18.2426 20 16.8284 20 14 20H10C7.17157 20 5.75736 20 4.87868 19.1213C4 18.2426 4 16.8284 4 14V6.78186Z"
          stroke="currentColor"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M4 14C4 14 7.73333 15 12 15C16.2667 15 20 14 20 14"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path d="M4.5 17.5H6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
        <path d="M18 17.5H19.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
        <path
          d="M11 17.5L13 17.5"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path d="M4 6H20" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.5" />
        <path d="M2 9L2 10" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
        <path d="M22 9L22 10" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
      </symbol>
      <symbol id="i-fuel" viewBox="0 0 24 24" fill="none">
        <path
          d="M10.4626 13L9.06858 14.8124C8.91919 15.0066 9.02626 15.2861 9.26987 15.3378L10.7301 15.6477C10.9899 15.7028 11.0889 16.0122 10.9073 16.2011L9.17773 18"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path d="M4 10H16" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
        <path
          d="M4 21L4 9C4 6.17157 4 4.75736 4.87868 3.87868C5.75736 3 7.17157 3 10 3C12.8284 3 14.2426 3 15.1213 3.87868C16 4.75736 16 6.17157 16 9L16 21H4Z"
          stroke="currentColor"
          strokeWidth="1.5"
        />
        <path d="M2 21H18" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
        <path
          d="M16 14H17.6667C17.9767 14 18.1317 14 18.2588 14.0341C18.6039 14.1265 18.8735 14.3961 18.9659 14.7412C19 14.8683 19 15.0233 19 15.3333V16.5C19 17.3284 19.6716 18 20.5 18C21.3284 18 22 17.3284 22 16.5V10.2111C22 9.60998 22 9.30941 21.9142 9.02598C21.8284 8.74255 21.6616 8.49247 21.3282 7.9923L20.5547 6.83205C20.2082 6.31223 19.6247 6 19 6"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-hotel" viewBox="0 0 24 24" fill="none">
        <path
          d="M3 4V20C3 20.9428 3 21.4142 3.29289 21.7071C3.58579 22 4.05719 22 5 22H19C19.9428 22 20.4142 22 20.7071 21.7071C21 21.4142 21 20.9428 21 20V4"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M10.5 8V9.5M10.5 11V9.5M13.5 8V9.5M13.5 11V9.5M10.5 9.5H13.5"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M14 22L14 17.9999C14 16.8954 13.1046 15.9999 12 15.9999C10.8954 15.9999 10 16.8954 10 17.9999V22"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M2 4H8C8.6399 2.82727 10.1897 2 12 2C13.8103 2 15.3601 2.82727 16 4H22"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M6 8H7M6 12H7M6 16H7"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M17 8H18M17 12H18M17 16H18"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-wallet" viewBox="0 0 24 24" fill="none">
        <path
          d="M14 3H5C3.89543 3 3 3.89543 3 5C3 6.10457 3.89543 7 5 7H18C18 6.07003 18 5.60504 17.8978 5.22354C17.6204 4.18827 16.8117 3.37962 15.7765 3.10222C15.395 3 14.93 3 14 3Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M3 5V15C3 17.8284 3 19.2426 3.87868 20.1213C4.75736 21 6.17157 21 9 21H15C17.8284 21 19.2426 21 20.1213 20.1213C21 19.2426 21 17.8284 21 15V13C21 10.1716 21 8.75736 20.1213 7.87868C19.2426 7 17.8284 7 15 7H7"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M21 12H19C18.535 12 18.3025 12 18.1118 12.0511C17.5941 12.1898 17.1898 12.5941 17.0511 13.1118C17 13.3025 17 13.535 17 14C17 14.465 17 14.6975 17.0511 14.8882C17.1898 15.4059 17.5941 15.8102 18.1118 15.9489C18.3025 16 18.535 16 19 16H21"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-bank" viewBox="0 0 24 24" fill="none">
        <path
          d="M12.125 5.75H12M12.25 5.75C12.25 5.88807 12.1381 6 12 6C11.8619 6 11.75 5.88807 11.75 5.75C11.75 5.61193 11.8619 5.5 12 5.5C12.1381 5.5 12.25 5.61193 12.25 5.75Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path d="M5 9V19M9 9V19" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
        <path
          d="M15 9V19M19 9V19"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M21.3518 9H2.64822C2.29022 9 2 8.70651 2 8.34447C2 8.12259 2.11099 7.91577 2.29495 7.79485L8.73007 3.56485C10.3171 2.52162 11.1107 2 12 2C12.8893 2 13.6829 2.52162 15.2699 3.56485L21.7051 7.79485C21.889 7.91577 22 8.12259 22 8.34447C22 8.70651 21.7098 9 21.3518 9Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M21.0397 20.2929L20.3519 19.5858C20.0707 19.2968 19.9301 19.1522 19.7514 19.0761C19.5726 19 19.3738 19 18.9762 19H5.02382C4.62621 19 4.4274 19 4.24863 19.0761C4.06987 19.1522 3.92929 19.2968 3.64814 19.5858L2.9603 20.2929C2.25356 21.0194 1.9002 21.3827 2.02456 21.6913C2.14893 22 2.64867 22 3.64814 22H20.3519C21.3513 22 21.8511 22 21.9754 21.6913C22.0998 21.3827 21.7464 21.0194 21.0397 20.2929Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-savings" viewBox="0 0 24 24" fill="none">
        <path
          d="M5 13.5H3C2.44772 13.5 2 13.9477 2 14.5V21C2 21.5523 2.44772 22 3 22H5C5.55228 22 6 21.5523 6 21V14.5C6 13.9477 5.55228 13.5 5 13.5Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M6 14.5H11.75C12.4404 14.5 13 15.0596 13 15.75C13 16.4404 12.4404 17 11.75 17H9.5"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M11 16.9998H14.6917C15.5417 16.9998 16.3697 16.729 17.0554 16.2267L19.6836 14.3015C20.2549 13.8584 21.0678 13.9088 21.5796 14.4192C22.1734 15.0112 22.1328 15.9828 21.4918 16.5236L17.0951 20.1022C16.3817 20.6828 15.49 20.9998 14.5701 20.9998H6"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M19 7C19 9.76133 16.7614 12 14 12C11.2386 12 9 9.76133 9 7C9 4.23857 11.2386 2 14 2C16.7614 2 19 4.23857 19 7Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-chart" viewBox="0 0 24 24" fill="none">
        <path
          d="M20.5 10.5V19.5C20.5 19.9659 20.5 20.1989 20.4239 20.3827C20.3224 20.6277 20.1277 20.8224 19.8827 20.9239C19.6989 21 19.4659 21 19 21C18.5341 21 18.3011 21 18.1173 20.9239C17.8723 20.8224 17.6776 20.6277 17.5761 20.3827C17.5 20.1989 17.5 19.9659 17.5 19.5V10.5C17.5 10.0341 17.5 9.80109 17.5761 9.61732C17.6776 9.37229 17.8723 9.17761 18.1173 9.07612C18.3011 9 18.5341 9 19 9C19.4659 9 19.6989 9 19.8827 9.07612C20.1277 9.17761 20.3224 9.37229 20.4239 9.61732C20.5 9.80109 20.5 10.0341 20.5 10.5Z"
          stroke="currentColor"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path d="M16.5 3H19.5V6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
        <path
          d="M19 3.5C19 3.5 15 8.5 4.5 12"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M13.5 14V19.5C13.5 19.9659 13.5 20.1989 13.4239 20.3827C13.3224 20.6277 13.1277 20.8224 12.8827 20.9239C12.6989 21 12.4659 21 12 21C11.5341 21 11.3011 21 11.1173 20.9239C10.8723 20.8224 10.6776 20.6277 10.5761 20.3827C10.5 20.1989 10.5 19.9659 10.5 19.5V14C10.5 13.5341 10.5 13.3011 10.5761 13.1173C10.6776 12.8723 10.8723 12.6776 11.1173 12.5761C11.3011 12.5 11.5341 12.5 12 12.5C12.4659 12.5 12.6989 12.5 12.8827 12.5761C13.1277 12.6776 13.3224 12.8723 13.4239 13.1173C13.5 13.3011 13.5 13.5341 13.5 14Z"
          stroke="currentColor"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M6.5 16.5V19.5C6.5 19.9659 6.5 20.1989 6.42388 20.3827C6.32239 20.6277 6.12771 20.8224 5.88268 20.9239C5.69891 21 5.46594 21 5 21C4.53406 21 4.30109 21 4.11732 20.9239C3.87229 20.8224 3.67761 20.6277 3.57612 20.3827C3.5 20.1989 3.5 19.9659 3.5 19.5V16.5C3.5 16.0341 3.5 15.8011 3.57612 15.6173C3.67761 15.3723 3.87229 15.1776 4.11732 15.0761C4.30109 15 4.53406 15 5 15C5.46594 15 5.69891 15 5.88268 15.0761C6.12771 15.1776 6.32239 15.3723 6.42388 15.6173C6.5 15.8011 6.5 16.0341 6.5 16.5Z"
          stroke="currentColor"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-clock" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.5" />
        <path d="M12 8V12L14 14" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
      </symbol>
      <symbol id="i-alert" viewBox="0 0 24 24" fill="none">
        <path
          d="M13.9248 21H10.0752C5.44476 21 3.12955 21 2.27636 19.4939C1.42317 17.9879 2.60736 15.9914 4.97574 11.9985L6.90057 8.75333C9.17559 4.91778 10.3131 3 12 3C13.6869 3 14.8244 4.91777 17.0994 8.75332L19.0243 11.9985C21.3926 15.9914 22.5768 17.9879 21.7236 19.4939C20.8704 21 18.5552 21 13.9248 21Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path d="M12 9V13" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
        <path
          d="M12.125 16.75H12M12.25 16.75C12.25 16.8881 12.1381 17 12 17C11.8619 17 11.75 16.8881 11.75 16.75C11.75 16.6119 11.8619 16.5 12 16.5C12.1381 16.5 12.25 16.6119 12.25 16.75Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-route" viewBox="0 0 24 24" fill="none">
        <circle
          cx="18"
          cy="5"
          r="3"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <circle
          cx="6"
          cy="19"
          r="3"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M12 5H8.5C6.567 5 5 6.567 5 8.5C5 10.433 6.567 12 8.5 12H15.5C17.433 12 19 13.567 19 15.5C19 17.433 17.433 19 15.5 19H12"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-shield" viewBox="0 0 24 24" fill="none">
        <path
          d="M18.7088 3.49534C16.8165 2.55382 14.5009 2 12 2C9.4991 2 7.1835 2.55382 5.29116 3.49534C4.36318 3.95706 3.89919 4.18792 3.4496 4.91378C3 5.63965 3 6.34248 3 7.74814V11.2371C3 16.9205 7.54236 20.0804 10.173 21.4338C10.9067 21.8113 11.2735 22 12 22C12.7265 22 13.0933 21.8113 13.8269 21.4338C16.4576 20.0804 21 16.9205 21 11.2371L21 7.74814C21 6.34249 21 5.63966 20.5504 4.91378C20.1008 4.18791 19.6368 3.95706 18.7088 3.49534Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-lock" viewBox="0 0 24 24" fill="none">
        <path
          d="M18.7088 3.49534C16.8165 2.55382 14.5009 2 12 2C9.4991 2 7.1835 2.55382 5.29116 3.49534C4.36318 3.95706 3.89919 4.18792 3.4496 4.91378C3 5.63965 3 6.34248 3 7.74814V11.2371C3 16.9205 7.54236 20.0804 10.173 21.4338C10.9067 21.8113 11.2735 22 12 22C12.7265 22 13.0933 21.8113 13.8269 21.4338C16.4576 20.0804 21 16.9205 21 11.2371L21 7.74814C21 6.34249 21 5.63966 20.5504 4.91378C20.1008 4.18791 19.6368 3.95706 18.7088 3.49534Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M10 10V8.5C10 7.39543 10.8954 6.5 12 6.5C13.1046 6.5 14 7.39543 14 8.5V10"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M14 10H10C9.17157 10 8.5 10.6716 8.5 11.5V13C8.5 13.8284 9.17157 14.5 10 14.5H14C14.8284 14.5 15.5 13.8284 15.5 13V11.5C15.5 10.6716 14.8284 10 14 10Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-undo" viewBox="0 0 24 24" fill="none">
        <path
          d="M3 12C3 16.9706 7.02944 21 12 21C16.9706 21 21 16.9706 21 12C21 7.02944 16.9706 3 12 3C8.79275 3 5.97733 4.67765 4.38341 7.20327M3.29339 3.00076L3.46556 5.05452C3.58958 6.53384 3.65159 7.27349 4.13359 7.68914C4.61559 8.10479 5.32673 8.03185 6.74899 7.88595L8.79339 7.67625"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-home" viewBox="0 0 24 24" fill="none">
        <path
          d="M3 11.9896V14.5C3 17.7998 3 19.4497 4.02513 20.4749C5.05025 21.5 6.70017 21.5 10 21.5H14C17.2998 21.5 18.9497 21.5 19.9749 20.4749C21 19.4497 21 17.7998 21 14.5V11.9896C21 10.3083 21 9.46773 20.6441 8.74005C20.2882 8.01237 19.6247 7.49628 18.2976 6.46411L16.2976 4.90855C14.2331 3.30285 13.2009 2.5 12 2.5C10.7991 2.5 9.76689 3.30285 7.70242 4.90855L5.70241 6.46411C4.37533 7.49628 3.71179 8.01237 3.3559 8.74005C3 9.46773 3 10.3083 3 11.9896Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-rain" viewBox="0 0 24 24" fill="none">
        <path
          d="M12.5 15L11.5 17M17 15L16 17M13.5 19L12.5 21M8 15L7 17M9 19L8 21"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M17.4776 8.89801L17.5 8.89795C19.9853 8.89795 22 10.8784 22 13.3214C22 14.8551 21.206 16.2065 20 17M17.4776 8.89801C17.4924 8.73611 17.5 8.57216 17.5 8.40646C17.5 5.42055 15.0376 3 12 3C9.12324 3 6.76233 5.17106 6.52042 7.93728M17.4776 8.89801C17.3753 10.0132 16.9286 11.0307 16.2428 11.8469M6.52042 7.93728C3.98398 8.17454 2 10.2745 2 12.8299C2 14.4378 2.78565 15.8652 4 16.7619M6.52042 7.93728C6.67826 7.92251 6.83823 7.91496 7 7.91496C8.12582 7.91496 9.16474 8.28072 10.0005 8.89795"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-traffic" viewBox="0 0 24 24" fill="none">
        <path
          d="M14.5 9H18C19.8856 9 20.8284 9 21.4142 9.58579C22 10.1716 22 11.1144 22 13V14H16M21 9L20.6431 7.21554C20.3353 5.67627 20.1813 4.90663 19.6284 4.45332C19.0754 4 18.2905 4 16.7208 4H13.0792C11.5095 4 10.7246 4 10.1716 4.45332C9.61867 4.90663 9.46475 5.67627 9.15689 7.21553L9 8"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M22 14V16H21V14H22Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M12 13H6C4.11438 13 3.17157 13 2.58579 13.5858C2 14.1716 2 15.1144 2 17V18H16V17C16 15.1144 16 14.1716 15.4142 13.5858C14.8284 13 13.8856 13 12 13Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M15 13L14.6431 11.2155C14.3353 9.67627 14.1813 8.90663 13.6284 8.45332C13.0754 8 12.2905 8 10.7208 8H7.27922C5.70946 8 4.92459 8 4.37163 8.45332C3.81867 8.90663 3.66475 9.67627 3.35689 11.2155L3 13"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M11 17H7L6 18H12L11 17Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M13.5 15.5V15.51"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M4.5 15.5V15.51"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M2 20V18H3V20H2Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M16 18V20H15V18H16Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M19.5004 11.5V11.51"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-send" viewBox="0 0 24 24" fill="none">
        <path
          d="M2.01733 17.4993C4.2169 17.4993 6.00001 19.2824 6.00001 21.4819"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M18 21.4819V21.39C18 19.2412 19.742 17.4993 21.8908 17.4993"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M6.00001 7.5166C6.00001 9.71617 4.2169 11.4993 2.01733 11.4993"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M18 7.5166C18 9.69692 19.769 11.468 21.9423 11.4989"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M17 7.50098C19.175 7.51308 20.3529 7.60953 21.1213 8.37792C22 9.2566 22 10.6708 22 13.4992V15.4992C22 18.3277 22 19.7419 21.1213 20.6206C20.2426 21.4992 18.8284 21.4992 16 21.4992H8C5.17157 21.4992 3.75736 21.4992 2.87868 20.6206C2 19.7419 2 18.3277 2 15.4992V13.4992C2 10.6708 2 9.2566 2.87868 8.37792C3.64706 7.60953 4.82497 7.51308 7 7.50098"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M15 14.4993C15 16.1561 13.6569 17.4993 12 17.4993C10.3431 17.4993 9 16.1561 9 14.4993C9 12.8424 10.3431 11.4993 12 11.4993C13.6569 11.4993 15 12.8424 15 14.4993Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M9.5 5.00098C9.5 5.00098 11.2998 2.50098 12 2.50098C12.7002 2.50098 14.5 5.00098 14.5 5.00098M12 8.00098V3.00098"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-link" viewBox="0 0 24 24" fill="none">
        <path
          d="M9.14339 10.691L9.35031 10.4841C11.329 8.50532 14.5372 8.50532 16.5159 10.4841C18.4947 12.4628 18.4947 15.671 16.5159 17.6497L13.6497 20.5159C11.671 22.4947 8.46279 22.4947 6.48405 20.5159C4.50532 18.5372 4.50532 15.329 6.48405 13.3503L6.9484 12.886"
          stroke="currentColor"
          strokeLinecap="round"
          strokeWidth="1.5"
        />
        <path
          d="M17.0516 11.114L17.5159 10.6497C19.4947 8.67095 19.4947 5.46279 17.5159 3.48405C15.5372 1.50532 12.329 1.50532 10.3503 3.48405L7.48405 6.35031C5.50532 8.32904 5.50532 11.5372 7.48405 13.5159C9.46279 15.4947 12.671 15.4947 14.6497 13.5159L14.8566 13.309"
          stroke="currentColor"
          strokeLinecap="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-group" viewBox="0 0 24 24" fill="none">
        <path
          d="M18.4995 20.5C18.2663 17.5685 15.8417 15.2477 12.808 15.0521L11.9995 15C11.7107 15.0076 11.4416 15.0178 11.1877 15.0298C8.18075 15.1723 5.7304 17.5974 5.49951 20.5"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M15.2495 9.25C15.2495 11.0449 13.7944 12.5 11.9995 12.5C10.2046 12.5 8.74952 11.0449 8.74952 9.25C8.74952 7.45507 10.2046 6 11.9995 6C13.7944 6 15.2495 7.45507 15.2495 9.25Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M5.50249 8.5C5.17908 7.99485 4.99158 7.39432 4.99158 6.75C4.99158 4.95507 6.44665 3.5 8.24157 3.5C8.68752 3.5 9.1125 3.58982 9.49939 3.75235"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M18.4963 8.5C18.8197 7.99485 19.0072 7.39432 19.0072 6.75C19.0072 4.95507 17.5521 3.5 15.7572 3.5C15.3113 3.5 14.8863 3.58982 14.4994 3.75235"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M22.0007 17.9996C21.8208 15.7374 19.9995 13.5 17.9995 13"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M1.99927 17.9996C2.17923 15.7374 4.00049 13.5 6.00049 13"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-tornado" viewBox="0 0 24 24" fill="none">
        <path
          d="M20 7C20 9.20914 16.4183 11 12 11C7.58172 11 4 9.20914 4 7C4 4.79086 7.58172 3 12 3C16.4183 3 20 4.79086 20 7Z"
          stroke="currentColor"
          strokeWidth="1.5"
        />
        <path
          d="M18 14C18 15.6569 15.3137 17 12 17C8.68629 17 6 15.6569 6 14C6 12.3431 8.68629 11 12 11"
          stroke="currentColor"
          strokeLinecap="round"
          strokeWidth="1.5"
        />
        <path
          d="M16 19C16 20.1046 14.2091 21 12 21C9.79086 21 8 20.1046 8 19C8 17.8954 9.79086 17 12 17"
          stroke="currentColor"
          strokeLinecap="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-nav" viewBox="0 0 24 24" fill="none">
        <path
          d="M11.922 4.79004C16.6963 3.16245 19.0834 2.34866 20.3674 3.63261C21.6513 4.91656 20.8375 7.30371 19.21 12.078L18.1016 15.3292C16.8517 18.9958 16.2267 20.8291 15.1964 20.9808C14.9195 21.0216 14.6328 20.9971 14.3587 20.9091C13.3395 20.5819 12.8007 18.6489 11.7231 14.783C11.4841 13.9255 11.3646 13.4967 11.0924 13.1692C11.0134 13.0742 10.9258 12.9866 10.8308 12.9076C10.5033 12.6354 10.0745 12.5159 9.21705 12.2769C5.35111 11.1993 3.41814 10.6605 3.0909 9.64127C3.00292 9.36724 2.97837 9.08053 3.01916 8.80355C3.17088 7.77332 5.00419 7.14834 8.6708 5.89838L11.922 4.79004Z"
          stroke="currentColor"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-calendar" viewBox="0 0 24 24" fill="none">
        <path d="M16 2V6M8 2V6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
        <path
          d="M13 4H11C7.22876 4 5.34315 4 4.17157 5.17157C3 6.34315 3 8.22876 3 12V14C3 17.7712 3 19.6569 4.17157 20.8284C5.34315 22 7.22876 22 11 22H13C16.7712 22 18.6569 22 19.8284 20.8284C21 19.6569 21 17.7712 21 14V12C21 8.22876 21 6.34315 19.8284 5.17157C18.6569 4 16.7712 4 13 4Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path d="M3 10H21" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
        <path
          d="M12.1258 14H12.0008M12.1258 18H12.0008M7.625 14H7.5M7.625 18H7.5M16.625 14H16.5M12.2508 14C12.2508 14.1381 12.1389 14.25 12.0008 14.25C11.8628 14.25 11.7508 14.1381 11.7508 14C11.7508 13.8619 11.8628 13.75 12.0008 13.75C12.1389 13.75 12.2508 13.8619 12.2508 14ZM12.2508 18C12.2508 18.1381 12.1389 18.25 12.0008 18.25C11.8628 18.25 11.7508 18.1381 11.7508 18C11.7508 17.8619 11.8628 17.75 12.0008 17.75C12.1389 17.75 12.2508 17.8619 12.2508 18ZM7.75 14C7.75 14.1381 7.63807 14.25 7.5 14.25C7.36193 14.25 7.25 14.1381 7.25 14C7.25 13.8619 7.36193 13.75 7.5 13.75C7.63807 13.75 7.75 13.8619 7.75 14ZM7.75 18C7.75 18.1381 7.63807 18.25 7.5 18.25C7.36193 18.25 7.25 18.1381 7.25 18C7.25 17.8619 7.36193 17.75 7.5 17.75C7.63807 17.75 7.75 17.8619 7.75 18ZM16.75 14C16.75 14.1381 16.6381 14.25 16.5 14.25C16.3619 14.25 16.25 14.1381 16.25 14C16.25 13.8619 16.3619 13.75 16.5 13.75C16.6381 13.75 16.75 13.8619 16.75 14Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-plus" viewBox="0 0 24 24" fill="none">
        <path
          d="M12.001 5.00003V19.002"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M19.002 12.002L4.99998 12.002"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-close" viewBox="0 0 24 24" fill="none">
        <path
          d="M18 6L6.00081 17.9992M17.9992 18L6 6.00085"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-phone" viewBox="0 0 24 24" fill="none">
        <path
          d="M13.5 2H10.5C8.14298 2 6.96447 2 6.23223 2.73223C5.5 3.46447 5.5 4.64298 5.5 7V17C5.5 19.357 5.5 20.5355 6.23223 21.2678C6.96447 22 8.14298 22 10.5 22H13.5C15.857 22 17.0355 22 17.7678 21.2678C18.5 20.5355 18.5 19.357 18.5 17V7C18.5 4.64298 18.5 3.46447 17.7678 2.73223C17.0355 2 15.857 2 13.5 2Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M12.125 19H12M12.25 19C12.25 19.1381 12.1381 19.25 12 19.25C11.8619 19.25 11.75 19.1381 11.75 19C11.75 18.8619 11.8619 18.75 12 18.75C12.1381 18.75 12.25 18.8619 12.25 19Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-piggy" viewBox="0 0 24 24" fill="none">
        <path
          d="M14.5 5.5H10.5C6.91015 5.5 4 8.41015 4 12C4 14.3012 5.19584 16.3231 7 17.4782L7.28751 19.2158C7.35758 19.6393 7.39262 19.851 7.4905 20.0143C7.6037 20.2031 7.77604 20.3492 7.98078 20.4301C8.1578 20.5 8.37243 20.5 8.80169 20.5C9.19947 20.5 9.39836 20.5 9.56635 20.4378C9.76071 20.3659 9.92792 20.2353 10.0449 20.0642C10.1459 19.9163 10.1942 19.7234 10.2906 19.3375L10.5 18.5H13.5L13.7094 19.3375C13.8058 19.7234 13.8541 19.9163 13.9551 20.0642C14.0721 20.2353 14.2393 20.3659 14.4337 20.4378C14.6016 20.5 14.8005 20.5 15.1983 20.5C15.6276 20.5 15.8422 20.5 16.0192 20.4301C16.224 20.3492 16.3963 20.2031 16.5095 20.0143C16.6074 19.851 16.6424 19.6393 16.7125 19.2158L17 17.4782C18.1096 16.7678 18.9891 15.7295 19.5018 14.5L20.3925 14.3217C21.162 14.1677 21.5468 14.0907 21.7734 13.8142C22 13.5378 22 13.1454 22 12.3606V12.0616C22 11.3116 22 10.9366 21.7882 10.6654C21.5764 10.3941 21.2126 10.3032 20.4851 10.1213L20 10C20 8.5 18.8333 7.16667 18 6.5V3.5H17.7361C16.3657 3.5 15.1129 4.27427 14.5 5.5Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M15.875 9.75H15.75M16 9.75C16 9.88807 15.8881 10 15.75 10C15.6119 10 15.5 9.88807 15.5 9.75C15.5 9.61193 15.6119 9.5 15.75 9.5C15.8881 9.5 16 9.61193 16 9.75Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M2 8V10C2 11.1046 2.89543 12 4 12"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-wheelchair" viewBox="0 0 24 24" fill="none">
        <path
          d="M13 16.5C13 19.5376 10.5376 22 7.5 22C4.46243 22 2 19.5376 2 16.5C2 13.4624 4.46243 11 7.5 11C10.5376 11 13 13.4624 13 16.5Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M22 20C22 21.1046 21.1046 22 20 22C18.8954 22 18 21.1046 18 20C18 18.8954 18.8954 18 20 18C21.1046 18 22 18.8954 22 20Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M13 14H16C16.93 14 17.395 14 17.7765 14.1022C18.8117 14.3796 19.6204 15.1883 19.8978 16.2235C20 16.605 20 17.07 20 18"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M5 11V5C5 4.06812 5 3.60218 4.84776 3.23463C4.64477 2.74458 4.25542 2.35523 3.76537 2.15224C3.39782 2 2.93188 2 2 2"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path d="M5 7H18" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
        <path d="M16 7V14" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
      </symbol>
      <symbol id="i-pin" viewBox="0 0 24 24" fill="none">
        <path
          d="M13 10C13 11.6569 11.6569 13 10 13C8.34315 13 7 11.6569 7 10C7 8.34315 8.34315 7 10 7C11.6569 7 13 8.34315 13 10Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M21.3547 16.4469L18.8796 14.3254C18.6347 14.1154 18.3226 14 18 14C17.6774 14 17.3653 14.1154 17.1204 14.3254L14.6453 16.4469C14.2357 16.7979 14 17.3105 14 17.8499V18.5752C14 19.9081 14 20.5746 14.305 21.0616C14.4655 21.3179 14.6821 21.5345 14.9384 21.695C15.4254 22 16.0919 22 17.4248 22H18.5752C19.9081 22 20.5746 22 21.0616 21.695C21.3179 21.5345 21.5345 21.3179 21.695 21.0616C22 20.5746 22 19.9081 22 18.5752V17.8499C22 17.3105 21.7643 16.7979 21.3547 16.4469Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path d="M18 19V22" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
        <path
          d="M18 10.0355C18 5.59762 14.4183 2 10 2C5.58172 2 2 5.59762 2 10.0355C2 12.5731 3 14.5462 5 16.3086C6.07535 17.2562 7.82291 19.0316 9.04653 20.5628C9.27943 20.8543 9.63972 21 10 21"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-tent" viewBox="0 0 24 24" fill="none">
        <path
          d="M10.2112 16.4234L8.00003 21L16 21L13.7889 16.4234C13.0083 14.8078 12.6181 14 12 14C11.382 14 10.9917 14.8078 10.2112 16.4234Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M9.99997 3L19.2905 14.8243C20.1372 15.9019 20.5605 16.4407 20.7803 17.076C21 17.7113 21 18.3965 21 19.7669V21"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M14 3L4.70943 14.8244C3.86277 15.902 3.43945 16.4407 3.21973 17.076C3.00002 17.7112 3.00001 18.3964 2.99999 19.7668L2.99997 21"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path d="M2 21H22" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
      </symbol>
      <symbol id="i-water" viewBox="0 0 24 24" fill="none">
        <path
          d="M17.4776 9.00915C17.485 9.00911 17.4925 9.00909 17.5 9.00909C19.9853 9.00909 22 11.0269 22 13.5159C22 15.8512 20.2265 17.7716 17.9548 18M17.4776 9.00915C17.4924 8.8442 17.5 8.67716 17.5 8.50834C17.5 5.46617 15.0376 3 12 3C9.12324 3 6.76233 5.21197 6.52042 8.03032M17.4776 9.00915C17.3753 10.1453 16.9286 11.182 16.2428 12.0136M6.52042 8.03032C3.98398 8.27205 2 10.4116 2 13.0152C2 15.4378 3.71776 17.536 6 18M6.52042 8.03032C6.67826 8.01527 6.83823 8.00758 7 8.00758C8.12582 8.00758 9.16474 8.38023 10.0005 9.00909"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M9.5 18.5034C9.5 17.2482 10.5532 16.0077 11.2924 15.2917C11.6939 14.9028 12.3061 14.9028 12.7076 15.2917C13.4468 16.0077 14.5 17.2482 14.5 18.5034C14.5 19.7341 13.5533 21 12 21C10.4467 21 9.5 19.7341 9.5 18.5034Z"
          stroke="currentColor"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-money" viewBox="0 0 24 24" fill="none">
        <path
          d="M14.4998 12.001C14.4998 13.3817 13.3805 14.501 11.9998 14.501C10.6191 14.501 9.49982 13.3817 9.49982 12.001C9.49982 10.6203 10.6191 9.50098 11.9998 9.50098C13.3805 9.50098 14.4998 10.6203 14.4998 12.001Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M16 5.00098C18.4794 5.00098 20.1903 5.38518 21.1329 5.6773C21.6756 5.84549 22 6.35987 22 6.92803V16.6833C22 17.7984 20.7719 18.6374 19.6762 18.4305C18.7361 18.253 17.5107 18.1104 16 18.1104C11.2491 18.1104 10.1096 19.9161 3.1448 18.3802C2.47265 18.232 2 17.6275 2 16.9392V6.92214C2 5.94628 2.92079 5.23464 3.87798 5.42458C10.1967 6.67844 11.4209 5.00098 16 5.00098Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M2 9.00098C3.95133 9.00098 5.70483 7.40605 5.92901 5.75514M18.5005 5.50098C18.5005 7.54062 20.2655 9.46997 22 9.46997M22 15.001C20.1009 15.001 18.2601 16.3112 18.102 18.0993M6.00049 18.4971C6.00049 16.2879 4.20963 14.4971 2.00049 14.4971"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-map" viewBox="0 0 24 24" fill="none">
        <path
          d="M5.25345 4.19584L4.02558 4.90813C3.03739 5.48137 2.54329 5.768 2.27164 6.24483C2 6.72165 2 7.30233 2 8.46368V16.6283C2 18.1542 2 18.9172 2.34226 19.3418C2.57001 19.6244 2.88916 19.8143 3.242 19.8773C3.77226 19.9719 4.42148 19.5953 5.71987 18.8421C6.60156 18.3306 7.45011 17.7994 8.50487 17.9435C8.98466 18.009 9.44231 18.2366 10.3576 18.6917L14.1715 20.588C14.9964 20.9982 15.004 21 15.9214 21H18C19.8856 21 20.8284 21 21.4142 20.4013C22 19.8026 22 18.8389 22 16.9117V10.1715C22 8.24423 22 7.2806 21.4142 6.68188C20.8284 6.08316 19.8856 6.08316 18 6.08316H15.9214C15.004 6.08316 14.9964 6.08139 14.1715 5.6712L10.8399 4.01463C9.44884 3.32297 8.75332 2.97714 8.01238 3.00117C7.27143 3.02521 6.59877 3.41542 5.25345 4.19584Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path d="M8 3L8 17.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
        <path
          d="M15 6.5L15 20.5"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-zap" viewBox="0 0 24 24" fill="none">
        <path
          d="M5.22576 11.3294L12.224 2.34651C12.7713 1.64397 13.7972 2.08124 13.7972 3.01707V9.96994C13.7972 10.5305 14.1995 10.985 14.6958 10.985H18.0996C18.8729 10.985 19.2851 12.0149 18.7742 12.6706L11.776 21.6535C11.2287 22.356 10.2028 21.9188 10.2028 20.9829V14.0301C10.2028 13.4695 9.80048 13.015 9.3042 13.015H5.90035C5.12711 13.015 4.71494 11.9851 5.22576 11.3294Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-heart" viewBox="0 0 24 24" fill="none">
        <path
          d="M13 20.3025C12.1525 20.6505 11.1746 20.5389 10.4107 19.9677C7.58942 17.858 2 13.0348 2 8.69444C2 5.82563 4.10526 3.5 7 3.5C8.5 3.5 10 4 12 6C14 4 15.5 3.5 17 3.5C19.8947 3.5 22 5.82563 22 8.69444C22 9.12591 21.9448 9.56214 21.8425 10"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M14 17C14 17 15 17 16 19C16 19 19.1765 14 22 13"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-plug" viewBox="0 0 24 24" fill="none">
        <path
          d="M4.51255 19.4866C7.02498 21.8794 10.016 20.9223 11.2124 19.9532C11.8314 19.4518 12.1097 19.1277 12.3489 18.8884C13.1864 18.1107 13.1326 17.3331 12.5882 16.711C12.3704 16.462 10.9731 15.1198 9.63313 13.7439C8.93922 13.0499 8.46066 12.5595 8.05149 12.1647C7.50354 11.6185 7.02499 10.9922 6.30715 11.0101C5.64913 11.0101 5.17057 11.5904 4.57237 12.1886C3.88422 12.8767 3.37598 13.7439 3.19652 14.5216C2.65814 16.7947 3.49562 18.4098 4.51255 19.4866ZM4.51255 19.4866L2.00012 21.999"
          stroke="currentColor"
          strokeLinecap="round"
          strokeWidth="1.5"
        />
        <path
          d="M19.4867 4.51472C16.9736 2.12078 13.9929 3.09593 12.7962 4.06548C12.177 4.56712 11.8987 4.89138 11.6593 5.13078C10.8216 5.90881 10.8755 6.68683 11.42 7.30926C11.4983 7.39881 11.7292 7.62975 12.055 7.95281M19.4867 4.51472C20.504 5.59199 21.3528 7.22547 20.8142 9.49971C20.6347 10.2777 20.1264 11.1453 19.438 11.8338C18.8397 12.4323 18.361 13.0128 17.7028 13.0128C16.9847 13.0308 16.6121 12.5115 16.064 11.9651M19.4867 4.51472L21.9999 2.0011M16.064 11.9651C15.6547 11.5701 15.07 10.9721 14.3759 10.2777C13.5175 9.39612 12.6355 8.52831 12.055 7.95281M16.064 11.9651L14.5024 13.4896M10.5114 9.50609L12.055 7.95281"
          stroke="currentColor"
          strokeLinecap="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-logout" viewBox="0 0 24 24" fill="none">
        <path
          d="M18 18C18 18.4644 18 18.6965 17.978 18.8918C17.7952 20.5145 16.5145 21.7952 14.8919 21.978C14.6965 22 14.4644 22 14 22H11C7.70017 22 6.05025 22 5.02513 20.9749C4 19.9498 4 18.2998 4 15L4.00001 8.99998C4.00001 5.70016 4.00003 4.05024 5.02514 3.02512C6.05027 2 7.70018 2 11 2H14C14.4644 2 14.6965 2 14.8919 2.02201C16.5145 2.20483 17.7952 3.48547 17.978 5.10816C18 5.30347 18 5.53565 18 6"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M8.07612 11.1183C8 11.3021 8 11.535 8 12.001C8 12.4669 8 12.6999 8.07612 12.8837C8.17761 13.1287 8.37229 13.3234 8.61732 13.4249C8.80109 13.501 9.03406 13.501 9.5 13.501H14.5C14.5002 15.2503 14.511 16.1299 15.0623 16.3858C15.0829 16.3954 15.1037 16.4042 15.1249 16.4124C15.7045 16.6353 16.3999 16.0139 17.7907 14.7711C19.2576 13.4602 19.9912 12.7851 20 11.957C19.9912 11.1289 19.2576 10.4538 17.7907 9.14301C16.3999 7.90018 15.7045 7.27876 15.1249 7.50171C15.1037 7.50985 15.0829 7.51869 15.0623 7.52822C14.5018 7.78844 14.5 8.69318 14.5 10.501H9.5C9.03406 10.501 8.80109 10.501 8.61732 10.5771C8.37229 10.6786 8.17761 10.8733 8.07612 11.1183Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-play" viewBox="0 0 24 24" fill="none">
        <path
          d="M18.8906 12.846C18.5371 14.189 16.8667 15.138 13.5257 17.0361C10.296 18.8709 8.6812 19.7884 7.37983 19.4196C6.8418 19.2671 6.35159 18.9776 5.95624 18.5787C5 17.6139 5 15.7426 5 12C5 8.2574 5 6.3861 5.95624 5.42132C6.35159 5.02245 6.8418 4.73288 7.37983 4.58042C8.6812 4.21165 10.296 5.12907 13.5257 6.96393C16.8667 8.86197 18.5371 9.811 18.8906 11.154C19.0365 11.7084 19.0365 12.2916 18.8906 12.846Z"
          stroke="currentColor"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-next" viewBox="0 0 24 24" fill="none">
        <path
          d="M15.9351 12.6258C15.6807 13.8374 14.327 14.7077 11.6198 16.4481C8.67528 18.3411 7.20303 19.2876 6.01052 18.9229C5.60662 18.7994 5.23463 18.5823 4.92227 18.2876C4 17.4178 4 15.6118 4 12C4 8.38816 4 6.58224 4.92227 5.71235C5.23463 5.41773 5.60662 5.20057 6.01052 5.07707C7.20304 4.71243 8.67528 5.6589 11.6198 7.55186C14.327 9.29233 15.6807 10.1626 15.9351 11.3742C16.0216 11.7865 16.0216 12.2135 15.9351 12.6258Z"
          stroke="currentColor"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path d="M20 5V19" stroke="currentColor" strokeLinecap="round" strokeWidth="1.5" />
      </symbol>
      <symbol id="i-refresh" viewBox="0 0 24 24" fill="none">
        <path
          d="M20.0092 2V5.13219C20.0092 5.42605 19.6418 5.55908 19.4537 5.33333C17.6226 3.2875 14.9617 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22C17.5228 22 22 17.5228 22 12"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-settings" viewBox="0 0 24 24" fill="none">
        <path d="M4 7H13M18 7H20M4 17H6M11 17H20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="15.5" cy="7" r="2.5" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="8.5" cy="17" r="2.5" stroke="currentColor" strokeWidth="1.5" />
      </symbol>
      <symbol id="i-pill" viewBox="0 0 24 24" fill="none">
        <rect
          x="2.8"
          y="8.3"
          width="18.4"
          height="7.4"
          rx="3.7"
          transform="rotate(-45 12 12)"
          stroke="currentColor"
          strokeWidth="1.5"
        />
        <path d="M9.4 9.4L14.6 14.6" stroke="currentColor" strokeWidth="1.5" />
      </symbol>
      <symbol id="i-thought" viewBox="0 0 24 24" fill="none">
        <path
          d="M7.5 15C5.01 15 3 13.21 3 11C3 8.97 4.69 7.29 6.89 7.04C7.6 4.72 9.86 3 12.5 3C15.37 3 17.76 4.97 18.19 7.57C19.84 8.07 21 9.47 21 11.1C21 13.25 19.1 15 16.75 15H7.5Z"
          stroke="currentColor"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <circle cx="7.5" cy="18.5" r="1.5" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="4.5" cy="21" r="0.75" fill="currentColor" />
      </symbol>
      <symbol id="i-chevron" viewBox="0 0 24 24" fill="none">
        <path
          d="M9 6C9 6 15 10.4189 15 12C15 13.5812 9 18 9 18"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-search" viewBox="0 0 24 24" fill="none">
        <path
          d="M17.5 17.5L22 22"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M20 11C20 6.02944 15.9706 2 11 2C6.02944 2 2 6.02944 2 11C2 15.9706 6.02944 20 11 20C15.9706 20 20 15.9706 20 11Z"
          stroke="currentColor"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-harbor" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="9.5" r="5.5" stroke="currentColor" strokeWidth="1.5" />
        <path d="M4 19.5H20" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </symbol>
      <symbol id="i-user" viewBox="0 0 24 24" fill="none">
        <path
          d="M20 21.0001C19.713 17.269 16.7289 14.3151 12.995 14.0662L12 13.9999C11.6446 14.0096 11.3134 14.0225 11.0008 14.0378C7.3 14.2192 4.28417 17.3057 4 21.0001"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <circle
          cx="12"
          cy="6.99988"
          r="4"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-external" viewBox="0 0 24 24" fill="none">
        <path
          d="M11.0991 3.00012C7.45013 3.00669 5.53932 3.09629 4.31817 4.31764C3.00034 5.63568 3.00034 7.75704 3.00034 11.9997C3.00034 16.2424 3.00034 18.3638 4.31817 19.6818C5.63599 20.9999 7.75701 20.9999 11.9991 20.9999C16.241 20.9999 18.3621 20.9999 19.6799 19.6818C20.901 18.4605 20.9906 16.5493 20.9972 12.8998"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M20.556 3.49612L11.0487 13.0586M20.556 3.49612C20.062 3.00151 16.7343 3.04761 16.0308 3.05762M20.556 3.49612C21.05 3.99074 21.0039 7.32273 20.9939 8.02714"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-activity" viewBox="0 0 24 24" fill="none">
        <path
          d="M4.31802 19.682C3 18.364 3 16.2426 3 12C3 7.75736 3 5.63604 4.31802 4.31802C5.63604 3 7.75736 3 12 3C16.2426 3 18.364 3 19.682 4.31802C21 5.63604 21 7.75736 21 12C21 16.2426 21 18.364 19.682 19.682C18.364 21 16.2426 21 12 21C7.75736 21 5.63604 21 4.31802 19.682Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M7 14L9.79289 11.2071C10.1834 10.8166 10.8166 10.8166 11.2071 11.2071L12.7929 12.7929C13.1834 13.1834 13.8166 13.1834 14.2071 12.7929L17 10"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
      <symbol id="i-forward" viewBox="0 0 24 24" fill="none">
        <path
          d="M21.8371 12.9178C21.5547 13.6884 20.7014 14.3047 18.9948 15.5372C16.6677 17.218 15.5041 18.0583 14.5312 17.9969C13.7882 17.9499 13.0976 17.6007 12.6223 17.0315C12 16.2863 12 14.8575 12 12C12 9.14246 12 7.71369 12.6223 6.96846C13.0976 6.39933 13.7882 6.0501 14.5312 6.00315C15.5041 5.94167 16.6677 6.78203 18.9948 8.46275C20.7014 9.6953 21.5547 10.3116 21.8371 11.0822C22.0543 11.675 22.0543 12.325 21.8371 12.9178Z"
          stroke="currentColor"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
        <path
          d="M11.8371 12.9178C11.5547 13.6884 10.7014 14.3047 8.99482 15.5372C6.66769 17.218 5.50413 18.0583 4.5312 17.9969C3.78818 17.9499 3.09758 17.6007 2.62232 17.0315C2 16.2863 2 14.8575 2 12C2 9.14246 2 7.71369 2.62232 6.96846C3.09758 6.39933 3.78818 6.0501 4.5312 6.00315C5.50413 5.94167 6.66769 6.78203 8.99482 8.46275C10.7014 9.6953 11.5547 10.3116 11.8371 11.0822C12.0543 11.675 12.0543 12.325 11.8371 12.9178Z"
          stroke="currentColor"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </symbol>
    </svg>
  );
}
