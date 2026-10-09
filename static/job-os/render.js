(function () {
  const esc = (value) => String(value == null ? '' : value).replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const labels = {dashboard: 'Dashboard', scout: 'Scout', pipeline: 'Pipeline', 'resume-studio': 'Resume Studio', logistics: 'Logistics', settings: 'Settings'};
  // Linear icons from mx-icons (MIT; see static/vendor/mx-icons/LICENSE), 24px grid.
  const icons = {
    dashboard: '<path d="M22 10.9V4.1C22 2.6 21.36 2 19.77 2H15.73C14.14 2 13.5 2.6 13.5 4.1V10.9C13.5 12.4 14.14 13 15.73 13H19.77C21.36 13 22 12.4 22 10.9Z"/><path d="M22 19.9V18.1C22 16.6 21.36 16 19.77 16H15.73C14.14 16 13.5 16.6 13.5 18.1V19.9C13.5 21.4 14.14 22 15.73 22H19.77C21.36 22 22 21.4 22 19.9Z"/><path d="M10.5 13.1V19.9C10.5 21.4 9.86 22 8.27 22H4.23C2.64 22 2 21.4 2 19.9V13.1C2 11.6 2.64 11 4.23 11H8.27C9.86 11 10.5 11.6 10.5 13.1Z"/><path d="M10.5 4.1V5.9C10.5 7.4 9.86 8 8.27 8H4.23C2.64 8 2 7.4 2 5.9V4.1C2 2.6 2.64 2 4.23 2H8.27C9.86 2 10.5 2.6 10.5 4.1Z"/>',
    scout: '<path d="M11.5 21C16.7467 21 21 16.7467 21 11.5C21 6.25329 16.7467 2 11.5 2C6.25329 2 2 6.25329 2 11.5C2 16.7467 6.25329 21 11.5 21Z"/><path d="M22 22L20 20"/>',
    pipeline: '<path d="M10.5 19.9V4.1C10.5 2.6 9.86 2 8.27 2H4.23C2.64 2 2 2.6 2 4.1V19.9C2 21.4 2.64 22 4.23 22H8.27C9.86 22 10.5 21.4 10.5 19.9Z"/><path d="M22 12.9V4.1C22 2.6 21.36 2 19.77 2H15.73C14.14 2 13.5 2.6 13.5 4.1V12.9C13.5 14.4 14.14 15 15.73 15H19.77C21.36 15 22 14.4 22 12.9Z"/>',
    'resume-studio': '<path d="M22 10V15C22 20 20 22 15 22H9C4 22 2 20 2 15V9C2 4 4 2 9 2H14"/><path d="M22 10H18C15 10 14 9 14 6V2L22 10Z"/><path d="M7 13H13"/><path d="M7 17H11"/>',
    applications: '<path d="M7.39999 6.32003L15.89 3.49003C19.7 2.22003 21.77 4.30003 20.51 8.11003L17.68 16.6C15.78 22.31 12.66 22.31 10.76 16.6L9.91999 14.08L7.39999 13.24C1.68999 11.34 1.68999 8.23003 7.39999 6.32003Z"/><path d="M10.11 13.6501L13.69 10.0601"/>',
    logistics: '<path d="M3.17004 7.43994L12 12.5499L20.77 7.46991"/><path d="M12 21.6099V12.5399"/><path d="M9.92999 2.48L4.59 5.45003C3.38 6.12003 2.39001 7.80001 2.39001 9.18001V14.83C2.39001 16.21 3.38 17.89 4.59 18.56L9.92999 21.53C11.07 22.16 12.94 22.16 14.08 21.53L19.42 18.56C20.63 17.89 21.62 16.21 21.62 14.83V9.18001C21.62 7.80001 20.63 6.12003 19.42 5.45003L14.08 2.48C12.93 1.84 11.07 1.84 9.92999 2.48Z"/><path d="M17 13.24V9.58002L7.51001 4.09998"/>',
    settings: '<path d="M12 15C13.6569 15 15 13.6569 15 12C15 10.3431 13.6569 9 12 9C10.3431 9 9 10.3431 9 12C9 13.6569 10.3431 15 12 15Z"/><path d="M2 12.8799V11.1199C2 10.0799 2.85 9.21994 3.9 9.21994C5.71 9.21994 6.45 7.93994 5.54 6.36994C5.02 5.46994 5.33 4.29994 6.24 3.77994L7.97 2.78994C8.76 2.31994 9.78 2.59994 10.25 3.38994L10.36 3.57994C11.26 5.14994 12.74 5.14994 13.65 3.57994L13.76 3.38994C14.23 2.59994 15.25 2.31994 16.04 2.78994L17.77 3.77994C18.68 4.29994 18.99 5.46994 18.47 6.36994C17.56 7.93994 18.3 9.21994 20.11 9.21994C21.15 9.21994 22.01 10.0699 22.01 11.1199V12.8799C22.01 13.9199 21.16 14.7799 20.11 14.7799C18.3 14.7799 17.56 16.0599 18.47 17.6299C18.99 18.5399 18.68 19.6999 17.77 20.2199L16.04 21.2099C15.25 21.6799 14.23 21.3999 13.76 20.6099L13.65 20.4199C12.75 18.8499 11.27 18.8499 10.36 20.4199L10.25 20.6099C9.78 21.3999 8.76 21.6799 7.97 21.2099L6.24 20.2199C5.33 19.6999 5.02 18.5299 5.54 17.6299C6.45 16.0599 5.71 14.7799 3.9 14.7799C2.85 14.7799 2 13.9199 2 12.8799Z"/>',
    total: '<path d="M7.99995 22H15.9999C20.0199 22 20.7399 20.39 20.9499 18.43L21.6999 10.43C21.9699 7.99 21.2699 6 16.9999 6H6.99995C2.72995 6 2.02995 7.99 2.29995 10.43L3.04995 18.43C3.25995 20.39 3.97995 22 7.99995 22Z"/><path d="M8 6V5.2C8 3.43 8 2 11.2 2H12.8C16 2 16 3.43 16 5.2V6"/><path d="M14 13V14C14 14.01 14 14.01 14 14.02C14 15.11 13.99 16 12 16C10.02 16 10 15.12 10 14.03V13C10 12 10 12 11 12H13C14 12 14 12 14 13Z"/><path d="M21.65 11C19.34 12.68 16.7 13.68 14 14.02"/><path d="M2.62 11.27C4.87 12.81 7.41 13.74 10 14.03"/>',
    active: '<path d="M9 22H15C20 22 22 20 22 15V9C22 4 20 2 15 2H9C4 2 2 4 2 9V15C2 20 4 22 9 22Z"/><path d="M7.33008 14.49L9.71008 11.4C10.0501 10.96 10.6801 10.88 11.1201 11.22L12.9501 12.66C13.3901 13 14.0201 12.92 14.3601 12.49L16.6701 9.51001"/>',
    attention: '<path d="M12 9V14"/><path d="M12.0001 21.41H5.94005C2.47005 21.41 1.02005 18.93 2.70005 15.9L5.82006 10.28L8.76006 5.00003C10.5401 1.79003 13.4601 1.79003 15.2401 5.00003L18.1801 10.29L21.3001 15.91C22.9801 18.94 21.5201 21.42 18.0601 21.42H12.0001V21.41Z"/><path d="M11.9945 17H12.0035"/>',
    applied: '<path d="M12 22C17.5 22 22 17.5 22 12C22 6.5 17.5 2 12 2C6.5 2 2 6.5 2 12C2 17.5 6.5 22 12 22Z"/><path d="M7.75 12L10.58 14.83L16.25 9.17004"/>',
    import: '<path d="M6 12H18"/><path d="M12 18V6"/>',
    board: '<path d="M10.5 19.9V4.1C10.5 2.6 9.86 2 8.27 2H4.23C2.64 2 2 2.6 2 4.1V19.9C2 21.4 2.64 22 4.23 22H8.27C9.86 22 10.5 21.4 10.5 19.9Z"/><path d="M22 12.9V4.1C22 2.6 21.36 2 19.77 2H15.73C14.14 2 13.5 2.6 13.5 4.1V12.9C13.5 14.4 14.14 15 15.73 15H19.77C21.36 15 22 14.4 22 12.9Z"/>',
    list: '<path d="M12 4.5H3"/><path d="M12 9.5H3"/><path d="M21 14.5H3"/><path d="M21 19.5H3"/>',
    pin: '<path d="M12 13.4299C13.7231 13.4299 15.12 12.0331 15.12 10.3099C15.12 8.58681 13.7231 7.18994 12 7.18994C10.2769 7.18994 8.88 8.58681 8.88 10.3099C8.88 12.0331 10.2769 13.4299 12 13.4299Z"/><path d="M3.62001 8.49C5.59001 -0.169998 18.42 -0.159997 20.38 8.5C21.53 13.58 18.37 17.88 15.6 20.54C13.59 22.48 10.41 22.48 8.39001 20.54C5.63001 17.88 2.47001 13.57 3.62001 8.49Z"/>',
    pay: '<path d="M17 20.5H7C4 20.5 2 19 2 15.5V8.5C2 5 4 3.5 7 3.5H17C20 3.5 22 5 22 8.5V15.5C22 19 20 20.5 17 20.5Z"/><path d="M12 15C13.6569 15 15 13.6569 15 12C15 10.3431 13.6569 9 12 9C10.3431 9 9 10.3431 9 12C9 13.6569 10.3431 15 12 15Z"/><path d="M2 9H3C6 9 7 8 7 5V4"/><path d="M22 9H21C18 9 17 8 17 5V4"/><path d="M2 15H3C6 15 7 16 7 19V20"/><path d="M22 15H21C18 15 17 16 17 19V20"/>',
    briefcase: '<path d="M7.99995 22H15.9999C20.0199 22 20.7399 20.39 20.9499 18.43L21.6999 10.43C21.9699 7.99 21.2699 6 16.9999 6H6.99995C2.72995 6 2.02995 7.99 2.29995 10.43L3.04995 18.43C3.25995 20.39 3.97995 22 7.99995 22Z"/><path d="M8 6V5.2C8 3.43 8 2 11.2 2H12.8C16 2 16 3.43 16 5.2V6"/><path d="M14 13V14C14 14.01 14 14.01 14 14.02C14 15.11 13.99 16 12 16C10.02 16 10 15.12 10 14.03V13C10 12 10 12 11 12H13C14 12 14 12 14 13Z"/><path d="M21.65 11C19.34 12.68 16.7 13.68 14 14.02"/><path d="M2.62 11.27C4.87 12.81 7.41 13.74 10 14.03"/>',
    external: '<path d="M12 2C6.48 2 2 6.48 2 12C2 17.52 6.48 22 12 22C17.52 22 22 17.52 22 12"/><path d="M13 11L21.2 2.80005"/><path d="M21.9999 6.83V2H17.1699"/>',
    edit: '<path d="M13.26 3.59997L5.04997 12.29C4.73997 12.62 4.43997 13.27 4.37997 13.72L4.00997 16.96C3.87997 18.13 4.71997 18.93 5.87997 18.73L9.09997 18.18C9.54997 18.1 10.18 17.77 10.49 17.43L18.7 8.73997C20.12 7.23997 20.76 5.52997 18.55 3.43997C16.35 1.36997 14.68 2.09997 13.26 3.59997Z"/><path d="M11.89 5.05005C12.32 7.81005 14.56 9.92005 17.34 10.2"/><path d="M3 22H21"/>',
    prev: '<path d="M15 19.9201L8.47997 13.4001C7.70997 12.6301 7.70997 11.3701 8.47997 10.6001L15 4.08008"/>',
    next: '<path d="M8.91003 19.9201L15.43 13.4001C16.2 12.6301 16.2 11.3701 15.43 10.6001L8.91003 4.08008"/>',
    expand: '<path d="M21 9V3H15"/><path d="M3 15V21H9"/><path d="M21 3L13.5 10.5"/><path d="M10.5 13.5L3 21"/>',
    magic: '<path d="M17.29 4.13999L17.22 7.92997C17.21 8.44997 17.54 9.13999 17.96 9.44999L20.44 11.33C22.03 12.53 21.77 14 19.87 14.6L16.64 15.61C16.1 15.78 15.53 16.37 15.39 16.92L14.62 19.86C14.01 22.18 12.49 22.41 11.23 20.37L9.46999 17.52C9.14999 17 8.39 16.61 7.79 16.64L4.45003 16.81C2.06003 16.93 1.38002 15.55 2.94002 13.73L4.92 11.43C5.29 11 5.46 10.2 5.29 9.65998L4.28005 6.42997C3.69005 4.52997 4.75004 3.47999 6.64004 4.09999L9.59005 5.06999C10.09 5.22999 10.84 5.11998 11.26 4.80998L14.34 2.58998C16 1.38998 17.33 2.08999 17.29 4.13999Z"/><path d="M21.91 22L18.88 18.97"/>',
    flash: '<path d="M6.08998 13.28H9.17998V20.48C9.17998 22.16 10.09 22.5 11.2 21.24L18.77 12.64C19.7 11.59 19.31 10.72 17.9 10.72H14.81V3.52002C14.81 1.84002 13.9 1.50002 12.79 2.76002L5.21998 11.36C4.29998 12.42 4.68998 13.28 6.08998 13.28Z"/>',
    refresh: '<path d="M22 12C22 17.52 17.52 22 12 22C6.48 22 3.11 16.44 3.11 16.44M3.11 16.44H7.63M3.11 16.44V21.44M2 12C2 6.48 6.44 2 12 2C18.67 2 22 7.56 22 7.56M22 7.56V2.56M22 7.56H17.56"/>',
    clock: '<path d="M12 9.66003V12.45L13.4 13.85"/><path d="M5.5 12C5.5 8.41 8.41 5.5 12 5.5C15.59 5.5 18.5 8.41 18.5 12C18.5 14.08 17.52 15.94 16 17.13H15.99C14.89 17.99 13.51 18.5 12 18.5C10.51 18.5 9.14 18 8.04 17.15H8.03C6.49 15.96 5.5 14.1 5.5 12Z"/><path d="M8.03003 17.15H8.04003C9.14003 18 10.51 18.5 12 18.5C13.51 18.5 14.89 17.99 15.99 17.13H16L15.49 19.6C15 21.5 13.9 22 12.55 22H11.46C10.11 22 9.00003 21.5 8.52003 19.59L8.03003 17.15Z"/><path d="M8.03003 6.85H8.04003C9.14003 6 10.51 5.5 12 5.5C13.51 5.5 14.89 6.01 15.99 6.87H16L15.49 4.4C15 2.5 13.9 2 12.55 2H11.46C10.11 2 9.00003 2.5 8.52003 4.41L8.03003 6.85Z"/>',
    eye: '<path d="M15.58 12C15.58 13.98 13.98 15.58 12 15.58C10.02 15.58 8.42004 13.98 8.42004 12C8.42004 10.02 10.02 8.42004 12 8.42004C13.98 8.42004 15.58 10.02 15.58 12Z"/><path d="M12 20.27C15.53 20.27 18.82 18.19 21.11 14.59C22.01 13.18 22.01 10.81 21.11 9.39997C18.82 5.79997 15.53 3.71997 12 3.71997C8.46997 3.71997 5.17997 5.79997 2.88997 9.39997C1.98997 10.81 1.98997 13.18 2.88997 14.59C5.17997 18.19 8.46997 20.27 12 20.27Z"/>',
    download: '<path d="M9 11V17L11 15"/><path d="M9 17L7 15"/><path d="M22 10V15C22 20 20 22 15 22H9C4 22 2 20 2 15V9C2 4 4 2 9 2H14"/><path d="M22 10H18C15 10 14 9 14 6V2L22 10Z"/>',
    radar: '<path d="M6 4C7.67 2.75 9.75 2 12 2C17.52 2 22 6.48 22 12C22 17.52 17.52 22 12 22C6.48 22 2 17.52 2 12C2 10.19 2.47999 8.48999 3.32999 7.01999L12 12"/><path d="M6.82999 8.95999C6.29999 9.84999 6 10.89 6 12C6 15.31 8.69 18 12 18C15.31 18 18 15.31 18 12C18 8.69 15.31 6 12 6C11.09 6 10.22 6.20001 9.45001 6.57001"/>',
    calendar: '<path d="M8 2V5"/><path d="M16 2V5"/><path d="M3.5 9.08997H20.5"/><path d="M21 8.5V17C21 20 19.5 22 16 22H8C4.5 22 3 20 3 17V8.5C3 5.5 4.5 3.5 8 3.5H16C19.5 3.5 21 5.5 21 8.5Z"/><path d="M15.6947 13.7H15.7037"/><path d="M15.6947 16.7H15.7037"/><path d="M11.9955 13.7H12.0045"/><path d="M11.9955 16.7H12.0045"/><path d="M8.29431 13.7H8.30329"/><path d="M8.29431 16.7H8.30329"/>',
    mail: '<path d="M17 20.5H7C4 20.5 2 19 2 15.5V8.5C2 5 4 3.5 7 3.5H17C20 3.5 22 5 22 8.5V15.5C22 19 20 20.5 17 20.5Z"/><path d="M17 9L13.87 11.5C12.84 12.32 11.15 12.32 10.12 11.5L7 9"/>',
    bell: '<path d="M12 6.43994V9.76994"/><path d="M12.02 2C8.34002 2 5.36002 4.98 5.36002 8.66V10.76C5.36002 11.44 5.08002 12.46 4.73002 13.04L3.46002 15.16C2.68002 16.47 3.22002 17.93 4.66002 18.41C9.44002 20 14.61 20 19.39 18.41C20.74 17.96 21.32 16.38 20.59 15.16L19.32 13.04C18.97 12.46 18.69 11.43 18.69 10.76V8.66C18.68 5 15.68 2 12.02 2Z"/><path d="M15.33 18.8201C15.33 20.6501 13.83 22.1501 12 22.1501C11.09 22.1501 10.25 21.7701 9.65004 21.1701C9.05004 20.5701 8.67004 19.7301 8.67004 18.8201"/>',
    chart: '<path d="M9 22H15C20 22 22 20 22 15V9C22 4 20 2 15 2H9C4 2 2 4 2 9V15C2 20 4 22 9 22Z"/><path d="M15.5 18.5C16.6 18.5 17.5 17.6 17.5 16.5V7.5C17.5 6.4 16.6 5.5 15.5 5.5C14.4 5.5 13.5 6.4 13.5 7.5V16.5C13.5 17.6 14.39 18.5 15.5 18.5Z"/><path d="M8.5 18.5C9.6 18.5 10.5 17.6 10.5 16.5V13C10.5 11.9 9.6 11 8.5 11C7.4 11 6.5 11.9 6.5 13V16.5C6.5 17.6 7.39 18.5 8.5 18.5Z"/>',
    cloud: '<path d="M6.36997 9.50993C2.28997 9.79993 2.29997 15.7099 6.36997 15.9999H16.03C17.2 16.0099 18.33 15.5699 19.2 14.7799C22.06 12.2799 20.53 7.27991 16.76 6.79991C15.41 -1.34009 3.61998 1.74993 6.40998 9.50993"/><path d="M12 16V19"/><path d="M12 23C13.1046 23 14 22.1046 14 21C14 19.8954 13.1046 19 12 19C10.8954 19 10 19.8954 10 21C10 22.1046 10.8954 23 12 23Z"/><path d="M18 21H14"/><path d="M10 21H6"/>',
    wallet: '<path d="M10.7516 16.8604V18.8904C10.7516 20.6104 9.15158 22.0004 7.18158 22.0004C5.21158 22.0004 3.60156 20.6104 3.60156 18.8904V16.8604C3.60156 18.5804 5.20158 19.8004 7.18158 19.8004C9.15158 19.8004 10.7516 18.5704 10.7516 16.8604Z"/><path d="M10.7501 14.11C10.7501 14.61 10.6101 15.07 10.3701 15.47C9.78006 16.44 8.57004 17.05 7.17004 17.05C5.77004 17.05 4.56003 16.43 3.97003 15.47C3.73003 15.07 3.59009 14.61 3.59009 14.11C3.59009 13.25 3.99007 12.48 4.63007 11.92C5.28007 11.35 6.17003 11.01 7.16003 11.01C8.15003 11.01 9.04006 11.36 9.69006 11.92C10.3501 12.47 10.7501 13.25 10.7501 14.11Z"/><path d="M10.7516 14.11V16.86C10.7516 18.58 9.15158 19.8 7.18158 19.8C5.21158 19.8 3.60156 18.57 3.60156 16.86V14.11C3.60156 12.39 5.20158 11 7.18158 11C8.17158 11 9.06161 11.35 9.71161 11.91C10.3516 12.47 10.7516 13.25 10.7516 14.11Z"/><path d="M22 10.9699V13.03C22 13.58 21.56 14.0299 21 14.0499H19.0399C17.9599 14.0499 16.97 13.2599 16.88 12.1799C16.82 11.5499 17.0599 10.9599 17.4799 10.5499C17.8499 10.1699 18.36 9.94995 18.92 9.94995H21C21.56 9.96995 22 10.4199 22 10.9699Z"/><path d="M2 10.5V8.5C2 5.78 3.64 3.88 6.19 3.56C6.45 3.52 6.72 3.5 7 3.5H16C16.26 3.5 16.51 3.50999 16.75 3.54999C19.33 3.84999 21 5.76 21 8.5V9.95001H18.92C18.36 9.95001 17.85 10.17 17.48 10.55C17.06 10.96 16.82 11.55 16.88 12.18C16.97 13.26 17.96 14.05 19.04 14.05H21V15.5C21 18.5 19 20.5 16 20.5H13.5"/>',
    ai: '<path d="M9.6 20H14.4C18.4 20 20 18.4 20 14.4V9.6C20 5.6 18.4 4 14.4 4H9.6C5.6 4 4 5.6 4 9.6V14.4C4 18.4 5.6 20 9.6 20Z"/><path d="M10.5 17H13.5C16 17 17 16 17 13.5V10.5C17 8 16 7 13.5 7H10.5C8 7 7 8 7 10.5V13.5C7 16 8 17 10.5 17Z"/><path d="M8.01001 4V2"/><path d="M12 4V2"/><path d="M16 4V2"/><path d="M20 8H22"/><path d="M20 12H22"/><path d="M20 16H22"/><path d="M16 20V22"/><path d="M12.01 20V22"/><path d="M8.01001 20V22"/><path d="M2 8H4"/><path d="M2 12H4"/><path d="M2 16H4"/><path d="M12 9.69995L11.06 11.34C10.85 11.7 11.02 12 11.44 12H12.56C12.98 12 13.15 12.3 12.94 12.66L12 14.3"/>',
    trash: '<path d="M21 5.97998C17.67 5.64998 14.32 5.47998 10.98 5.47998C9 5.47998 7.02 5.57998 5.04 5.77998L3 5.97998"/><path d="M8.5 4.97L8.72 3.66C8.88 2.71 9 2 10.69 2H13.31C15 2 15.13 2.75 15.28 3.67L15.5 4.97"/><path d="M18.85 9.14001L18.2 19.21C18.09 20.78 18 22 15.21 22H8.79002C6.00002 22 5.91002 20.78 5.80002 19.21L5.15002 9.14001"/><path d="M10.33 16.5H13.66"/><path d="M9.5 12.5H14.5"/>',
    close: '<path d="M12 22C17.5 22 22 17.5 22 12C22 6.5 17.5 2 12 2C6.5 2 2 6.5 2 12C2 17.5 6.5 22 12 22Z"/><path d="M9.16998 14.83L14.83 9.17004"/><path d="M14.83 14.83L9.16998 9.17004"/>',
  };
  // mx-icons are drawn for 24px at a 1.5 stroke; smaller sizes get a heavier
  // stroke so the line still lands at about 1.3 device pixels and stays crisp.
  const strokeFor = (size) => (size <= 15 ? 2 : size <= 18 ? 1.8 : size <= 21 ? 1.65 : 1.5);
  const icon = (name, size) => `<svg class="mx-icon" width="${size || 16}" height="${size || 16}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${strokeFor(size || 16)}" stroke-linecap="round" stroke-linejoin="round" shape-rendering="geometricPrecision" aria-hidden="true">${icons[name] || ''}</svg>`;
  // Lifecycle statuses grouped into the tones a reader scans for.
  const tones = {
    discovered: 'neutral', scraped: 'neutral', analyzed: 'neutral', shortlisted: 'favorite',
    tailoring: 'favorite', resume_ready: 'accent', application_ready: 'accent', applying: 'accent',
    awaiting_approval: 'warn',
    submitted: 'info', rejected: 'danger', screening: 'success', interviewing: 'success',
    offer: 'offer', offer_accepted: 'offer',
    skipped: 'muted', expired: 'muted', closed: 'muted', withdrawn: 'muted', no_response: 'muted',
  };
  const APPLIED = ['submitted', 'screening', 'interviewing', 'offer', 'offer_accepted'];
  // The board's columns and the statuses each holds (api/job_os/applications.py COLUMNS).
  const STAGES = [
    ['new', 'New', ['discovered', 'scraped', 'analyzed']],
    ['favorite', 'Favorite', ['shortlisted']],
    ['ready', 'Ready to apply', ['tailoring', 'resume_ready', 'application_ready', 'awaiting_approval', 'applying']],
    ['applied', 'Applied', ['submitted']],
    ['rejected', 'Rejected', ['rejected']],
    ['interview', 'Interview', ['screening', 'interviewing']],
    ['offers', 'Offer', ['offer', 'offer_accepted', 'offer_declined']],
    ['closed', 'Closed', ['withdrawn', 'no_response', 'closed', 'skipped', 'expired']],
  ];
  // Names that match the board's columns ("Favorite", not "Shortlisted").
  const STATUS_NAMES = {shortlisted: 'Favorite', resume_ready: 'Resume ready', application_ready: 'Ready to apply',
    submitted: 'Applied', interviewing: 'Interview', no_response: 'No response', offer_accepted: 'Offer accepted', offer_declined: 'Offer declined'};
  // Dashboard tiles open the Pipeline list narrowed to a group of statuses.
  const STATUS_GROUPS = {
    active: {label: 'Active work', statuses: ['tailoring', 'resume_ready', 'application_ready', 'awaiting_approval', 'applying'],
      empty: 'Jobs show here while Luna tailors a resume for them and until you apply. Tailor one from Resume Studio or a job’s card.'},
    applied: {label: 'Applied', statuses: APPLIED.concat(['offer_declined', 'rejected', 'no_response', 'withdrawn']),
      empty: 'Jobs you have applied for show here. Drag a card to Applied on the board, or choose Mark applied on a job.'},
  };
  const statusLabel = (status) => {
    if (STATUS_GROUPS[status]) return STATUS_GROUPS[status].label;
    if (STATUS_NAMES[status]) return STATUS_NAMES[status];
    const text = String(status || '').replace(/_/g, ' ');
    return text.charAt(0).toUpperCase() + text.slice(1);
  };
  // The shared "working" line (micro.js): a shimmering status that steps through
  // what Luna or Scout is doing. Plain text if micro.js did not load.
  const statusLine = (messages, cls) => (window.Micro ? window.Micro.status(messages, cls) : `<span class="${cls || ''}">${esc([].concat(messages)[0])}</span>`);
  const badge = (status) => `<span class="job-os-badge" data-tone="${tones[status] || 'neutral'}">${esc(statusLabel(status))}</span>`;
  function until(epochSeconds) {
    const seconds = Number(epochSeconds || 0) - Math.floor(Date.now() / 1000);
    if (!epochSeconds) return '';
    if (seconds < 90) return 'any moment';
    if (seconds < 3600) return 'in ' + Math.round(seconds / 60) + 'm';
    if (seconds < 86400) return 'in ' + Math.round(seconds / 3600) + 'h';
    return 'in ' + Math.round(seconds / 86400) + 'd';
  }
  // Settings section each automation is configured in.
  const AUTOMATION_SECTION = {scout: 'scout', analysis: 'ai', alerts: 'notifications', digest: 'notifications', replies: 'notifications'};
  function automationsCard(items) {
    if (!items) return '';
    const rows = items.map((a, i) => {
      const last = typeof a.last === 'number' ? `Last ${when(a.last)}` : a.last ? `Last ${esc(a.last)}` : '';
      const timing = [last, a.next ? `next ${until(a.next)}` : ''].filter(Boolean).join(' · ');
      const note = a.on ? [a.detail, timing].filter(Boolean).join(' · ') : a.off_reason;
      // The last 14 days as a row of ticks (as on a status page): green ran fine, red failed, amber both, grey nothing.
      const days = a.history || [];
      const fmt = (d) => new Date(`${d.day}T12:00:00`).toLocaleDateString(undefined, {month: 'short', day: 'numeric'});
      const tickTip = (d) => `${fmt(d)}: ${d.state === 'none' ? 'nothing ran' : [d.ok && `${d.ok} ok`, d.failed && `${d.failed} failed`].filter(Boolean).join(', ')}`;
      const ok = days.reduce((n, d) => n + d.ok, 0), bad = days.reduce((n, d) => n + d.failed, 0);
      const ticks = days.length ? `<span class="automation-ticks" role="img" aria-label="Last ${days.length} days: ${ok} ok, ${bad} failed">${days.map((d) => `<i data-state="${esc(d.state)}" title="${esc(tickTip(d))}"></i>`).join('')}</span>` : '';
      return `<button type="button" class="automation-row" data-job-os-action="settings-focus" data-section="${esc(AUTOMATION_SECTION[a.key] || 'scout')}" data-on="${a.on ? 'true' : 'false'}" style="--i:${i}" title="Edit ${esc(a.label)}"><span class="automation-dot" aria-hidden="true"></span><strong class="automation-title">${esc(a.label)}</strong><span class="automation-end"><span class="automation-state">${a.on ? 'On' : 'Off'}</span><span class="automation-edit" aria-hidden="true">${icon('edit', 16)}</span></span><span class="automation-main"><small>${esc(a.schedule)}</small>${note ? `<small class="automation-note">${esc(note)}</small>` : ''}</span>${ticks}</button>`;
    }).join('');
    return `<section class="job-os-card automations-card">${cardHead('Automations', 'flash', `<button type="button" class="job-os-icon-btn" data-job-os-view="settings" aria-label="Automation settings" title="Automation settings">${icon('settings', 18)}</button>`)}<div class="automations">${rows}</div></section>`;
  }
  // While a view's data is on its way: the same spinner the app's other pages show.
  const LOADING = '<div class="loading-spinner-wrap job-os-loading" role="status"><div class="loading-spinner" aria-hidden="true"></div><span class="sr-only">Loading</span></div>';
  // A card's title row: an icon chip, the title (with an optional count) and actions on the right.
  function cardHead(title, iconName, actions, count) {
    return `<div class="job-os-card-head"><h2>${iconName ? `<span class="card-icon" aria-hidden="true">${icon(iconName, 16)}</span>` : ''}<span class="card-title">${esc(title)}</span>${count != null ? `<span class="job-os-count">${Number(count)}</span>` : ''}</h2>${actions ? `<div class="card-head-actions">${actions}</div>` : ''}</div>`;
  }
  // Ten rows a page; the pager says where you are and steps through the rest.
  const PAGE = 10;
  function paged(items, page) {
    const pages = Math.max(1, Math.ceil(items.length / PAGE));
    const at = Math.min(Math.max(0, Number(page) || 0), pages - 1);
    return {rows: items.slice(at * PAGE, at * PAGE + PAGE), at, pages, total: items.length};
  }
  function pager(key, p) {
    if (p.pages <= 1) return '';
    const btn = (to, label, iconName, disabled) => `<button type="button" class="job-os-icon-btn" data-job-os-action="page" data-pager="${key}" data-page="${to}" aria-label="${label}" title="${label}" ${disabled ? 'disabled' : ''}>${icon(iconName, 15)}</button>`;
    const numbers = Array.from({length: p.pages}, (_, i) => i).filter((i) => p.pages <= 7 || i === 0 || i === p.pages - 1 || Math.abs(i - p.at) <= 1);
    const dots = [];
    numbers.forEach((i, n) => {
      if (n && i - numbers[n - 1] > 1) dots.push('<span class="pager-gap">…</span>');
      dots.push(`<button type="button" class="pager-num${i === p.at ? ' active' : ''}" data-job-os-action="page" data-pager="${key}" data-page="${i}"${i === p.at ? ' aria-current="page"' : ''}>${i + 1}</button>`);
    });
    return `<nav class="pager" aria-label="Pages"><span class="pager-range">${p.at * PAGE + 1}–${Math.min(p.total, p.at * PAGE + PAGE)} of ${p.total}</span><span class="pager-buttons">${btn(p.at - 1, 'Previous page', 'prev', p.at === 0)}${dots.join('')}${btn(p.at + 1, 'Next page', 'next', p.at >= p.pages - 1)}</span></nav>`;
  }
  function when(epochSeconds) {
    const seconds = Math.max(0, Math.floor(Date.now() / 1000) - Number(epochSeconds || 0));
    if (!epochSeconds) return '';
    if (seconds < 60) return 'Just now';
    if (seconds < 3600) return Math.floor(seconds / 60) + 'm ago';
    if (seconds < 86400) return Math.floor(seconds / 3600) + 'h ago';
    if (seconds < 86400 * 7) return Math.floor(seconds / 86400) + 'd ago';
    return new Date(epochSeconds * 1000).toLocaleDateString(undefined, {month: 'short', day: 'numeric'});
  }
  // The API lists jobs oldest first (created_at ASC); every view here reads newest first.
  const newestFirst = (jobs) => jobs.slice().sort((a, b) => (Number(b.updated_at) || 0) - (Number(a.updated_at) || 0) || (Number(b.created_at) || 0) - (Number(a.created_at) || 0));
  const dashboardOf = (state) => state.dashboard || {total_jobs: 0, active_work: 0, needs_attention: 0, by_status: {}};
  // Job sites Scout reads itself (api/job_os/site_health.py): any that no longer read correctly.
  const siteProblems = (state) => ((dashboardOf(state).site_health) || []).filter((site) => site.state && site.state !== 'ok');
  const SITE_STATE = {changed: 'Site changed', unreachable: 'Not reachable', ok: 'Working'};
  function siteHealthBanner(state, where) {
    return siteProblems(state).filter((site) => site.in_use !== false).map((site) => {
      const changed = site.state === 'changed';
      const since = site.since ? new Date(site.since * 1000).toLocaleDateString(undefined, {day: 'numeric', month: 'short'}) : '';
      const what = changed ? `${esc(site.name)} has changed its pages, so Scout can no longer read it. Its searches find nothing until its reader is updated.`
        : `${esc(site.name)} has not loaded for the last few tries. It may be down; Scout keeps trying.`;
      return `<div class="site-health-banner" data-state="${esc(site.state)}" data-key="site-health-${esc(site.site)}-${where}" role="alert">
        <span class="site-health-icon" aria-hidden="true">${icon('close', 18)}</span>
        <div class="site-health-text"><strong>${esc(site.name)}: ${SITE_STATE[site.state] || esc(site.state)}${since ? ` <small>since ${esc(since)}</small>` : ''}</strong><span>${what}</span></div>
        <div class="site-health-actions"><button type="button" class="job-os-btn" data-job-os-action="site-check" data-site="${esc(site.site)}">Check now</button></div></div>`;
    }).join('');
  }
  const appliedCount = (byStatus) => STATUS_GROUPS.applied.statuses.reduce((sum, key) => sum + (byStatus[key] || 0), 0);
  const WORKPLACE = {remote: 'Remote', hybrid: 'Hybrid', onsite: 'On-site'};
  function jobChips(job) {
    const chips = [];
    if (job.workplace) chips.push(`<span class="job-os-chip" data-kind="${esc(job.workplace)}">${esc(WORKPLACE[job.workplace] || job.workplace)}</span>`);
    if (job.salary_text) chips.push(`<span class="job-os-chip" data-kind="pay">${esc(job.salary_text)}</span>`);
    if (job.employment_type) chips.push(`<span class="job-os-chip">${esc(job.employment_type)}</span>`);
    return chips.length ? `<span class="job-os-chips">${chips.join('')}</span>` : '';
  }
  // Match bands for Luna's 0-100 fit score of the master resume against a job:
  // green from 75, yellow from 50, red below.
  const BANDS = [[75, 'good', 'Good match'], [50, 'fair', 'Needs improvement'], [0, 'poor', 'Terrible match']];
  const band = (score) => BANDS.find(([min]) => Number(score) >= min) || BANDS[BANDS.length - 1];
  // Fit score ring: the arc fills to the score, coloured by its band.
  const analysing = (job) => !!(job.analysis && (job.analysis.status === 'pending' || job.analysis.status === 'running'));
  // The score ring drawn like Resume Studio's: a track, and the arc to the score
  // with rounded ends in its band colour (no glow at this size).
  const ringSvg = (fit) => `<svg class="fit-ring-svg" viewBox="0 0 40 40" aria-hidden="true"><circle class="fit-ring-track" cx="20" cy="20" r="16"/>${fit == null ? '' : `<circle class="fit-ring-arc" cx="20" cy="20" r="16" pathLength="100" style="--fit:${fit}"/>`}</svg>`;
  function fitRing(a, size) {
    if (!a) return '';
    if (a.status === 'pending' || a.status === 'running') return `<span class="fit-ring ${size || ''} is-busy" title="Luna is scoring your resume against this job" aria-label="Scoring">${ringSvg(25)}<span>…</span></span>`;
    if (a.status === 'failed') return `<span class="fit-ring ${size || ''} is-failed" title="Scoring failed" aria-label="Scoring failed">${ringSvg(100)}<span>!</span></span>`;
    if (a.fit_score == null) return '';
    const [, key, text] = band(a.fit_score);
    const score = Number(a.fit_score);
    return `<span class="fit-ring ${size || ''}" data-band="${key}" title="${esc(text)} · ${score}%" aria-label="${esc(text)}, ${score} percent">${ringSvg(Math.max(score, 1))}<span>${score}</span></span>`;
  }
  const emptyRing = (cls, mark) => `<span class="fit-ring${cls || ''}">${ringSvg(/is-busy/.test(cls || '') ? 25 : /is-failed/.test(cls || '') ? 100 : null)}<span>${mark}</span></span>`;
  // Job sites come from the server (api/job_os/apify.py SITES); these are the
  // names to fall back on before it answers.
  let SITES = [['indeed', 'Indeed'], ['linkedin', 'LinkedIn']];
  const SOURCE_LABEL = {indeed: 'Indeed', linkedin: 'LinkedIn', remoteid: 'remote.id', manual: 'Manual'};
  let SITE_COUNTRIES = {}; // site -> countries it covers (absent = any)
  let SITE_DIRECT = new Set(['remoteid']); // read straight from the site, with or without Apify
  function useSites(list) {
    if (!Array.isArray(list) || !list.length) return;
    SITES = list.map((site) => [site.key, site.name]);
    SITE_DIRECT = new Set(list.filter((site) => site.key !== 'indeed' && site.needs_apify === false).map((site) => site.key));
    SITE_COUNTRIES = Object.fromEntries(list.filter((site) => site.countries).map((site) => [site.key, site.countries]));
    list.forEach((site) => { SOURCE_LABEL[site.key] = site.name; });
  }
  // Scout's finds carry their job site; anything older or unknown reads as Indeed.
  const sourceOf = (job) => (SOURCE_LABEL[job.source] ? job.source : 'indeed');
  // "Kuala Lumpur, M14, MY" + "Malaysia" reads as "Kuala Lumpur, Malaysia":
  // Indeed's region and country codes add nothing next to the country name.
  function place(job) {
    const parts = String(job.location || '').split(',').map((p) => p.trim()).filter((p) => p && !/^[A-Z0-9]{1,3}$/.test(p));
    if (job.country && !parts.some((p) => p.toLowerCase() === String(job.country).toLowerCase())) parts.push(job.country);
    return parts.join(', ');
  }
  function jobCard(job) {
    const initial = String(job.company || job.title || '?').trim().charAt(0).toUpperCase() || '?';
    const meta = [job.company || 'Company to review', place(job), SOURCE_LABEL[sourceOf(job)]].filter(Boolean).map(esc).join(' · ');
    return `<button class="job-os-job-card${analysing(job) ? ' is-analysing' : ''}" type="button" data-job-id="${esc(job.id)}" data-key="job-${esc(job.id)}">${fitRing(job.analysis, 'small') || `<span class="job-os-job-avatar" aria-hidden="true">${esc(initial)}</span>`}<span class="job-os-job-main"><strong>${esc(job.title)}</strong><span>${meta}</span>${jobChips(job)}</span>${badge(job.status)}<small class="job-os-job-when">${esc(when(job.updated_at))}</small></button>`;
  }
  function jobList(jobs, emptyTitle, emptyBody) {
    return jobs.length
      ? `<div class="job-os-list" role="list">${jobs.map(jobCard).join('')}</div>`
      : `<div class="job-os-empty"><strong>${esc(emptyTitle)}</strong><p>${esc(emptyBody)}</p></div>`;
  }
  // Firecrawl health, as the server classified it (see api/job_os/firecrawl.py).
  const FIRECRAWL_LABELS = {healthy: 'Firecrawl ready', offline: 'Firecrawl offline', incompatible: 'Firecrawl incompatible', not_configured: 'Firecrawl not set up'};
  function header(title, subtitle, state) {
    const ready = state.capability && state.capability.available;
    const fc = state.firecrawl;
    const ap = state.apifyUsage;
    // With Apify on, Scout doesn't use Firecrawl: the chip shows Apify and its spend.
    const chip = !ready
      ? '<span class="job-os-status" data-ready="false">Storage unavailable</span>'
      : ap && ap.active
        ? `<button type="button" class="job-os-status" data-ready="${ap.usage && ap.usage.warn ? 'false' : 'true'}" data-job-os-view="settings" title="Scout runs on Apify${ap.usage ? ` · this month $${ap.usage.used_usd} of $${ap.usage.limit_usd}` : ''}">${ap.usage ? `Apify · $${ap.usage.used_usd.toFixed(2)} of $${ap.usage.limit_usd.toFixed(0)}` : 'Apify ready'}</button>`
      : fc
        ? `<button type="button" class="job-os-status" data-ready="${fc.state === 'healthy' ? 'true' : 'false'}" data-fc-state="${esc(fc.state)}" data-job-os-view="settings" title="${esc(fc.detail || '')}">${esc(FIRECRAWL_LABELS[fc.state] || 'Firecrawl unknown')}</button>`
        : '<span class="job-os-status" data-ready="true">Ready</span>';
    return `<header class="job-os-header"><div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div>${chip}</header>`;
  }
  // Narrow screens put the side panel in a drawer, so they keep a compact
  // section switcher in the page itself.
  // Sections in the side panel and the phone switcher; Logistics can be hidden in Settings.
  const sectionsOf = (state) => Object.keys(labels).filter((key) => key !== 'logistics' || state.showLogistics !== false);
  function mobileNav(view, state) {
    // Phones: a tab bar along the bottom of the screen, as in a native app.
    const short = {dashboard: 'Home', 'resume-studio': 'Resume'};
    return `<nav class="job-os-tabs" aria-label="Job OS sections" data-mi-tabs>${sectionsOf(state || {}).map((key) => `<button type="button" class="${view === key ? 'active' : ''}" data-job-os-view="${key}"${view === key ? ' aria-current="page"' : ''}>${icon(key, 20)}<span>${short[key] || labels[key]}</span></button>`).join('')}</nav>`;
  }
  function metric(name, value, label, target) {
    return `<button type="button" class="job-os-metric" ${target}><img class="job-os-metric-icon" data-metric="${name}" src="/static/job-os-metric-${name}.png" alt="" aria-hidden="true"><span class="job-os-metric-body"><strong data-count-key="jobs-${name}">${esc(value)}</strong><span>${esc(label)}</span></span></button>`;
  }
  function placeholder(view, body) {
    return `<section class="job-os-card job-os-placeholder"><span class="job-os-placeholder-icon">${icon(view, 26)}</span><h2>${esc(labels[view])}</h2><p>${esc(body)}</p><button class="job-os-btn" type="button" data-job-os-view="dashboard">Back to dashboard</button></section>`;
  }

  // ---- Settings ----------------------------------------------------------
  // Every input carries data-setting="section.key"; index.js serialises the
  // form back into a partial settings object by that path.
  const get = (obj, path) => path.split('.').reduce((acc, key) => (acc == null ? acc : acc[key]), obj);
  function toggle(path, label, value, hint) {
    return `<label class="job-os-toggle"><input type="checkbox" data-setting="${path}" ${value ? 'checked' : ''}><span class="job-os-toggle-track" aria-hidden="true"></span><span class="job-os-toggle-text"><strong>${esc(label)}</strong>${hint ? `<small>${esc(hint)}</small>` : ''}</span></label>`;
  }
  function numberField(path, label, value, min, max, suffix) {
    return `<label class="job-os-field"><span>${esc(label)}</span><span class="job-os-field-input"><input type="number" data-setting="${path}" value="${esc(value)}" min="${min}" max="${max}" step="1" inputmode="numeric">${suffix ? `<em>${esc(suffix)}</em>` : ''}</span></label>`;
  }
  function textField(path, label, value, placeholderText, type) {
    return `<label class="job-os-field"><span>${esc(label)}</span><input type="${type || 'text'}" data-setting="${path}" value="${esc(value)}" placeholder="${esc(placeholderText || '')}" autocomplete="off" spellcheck="false"></label>`;
  }
  function selectField(path, label, value, options) {
    return `<label class="job-os-field"><span>${esc(label)}</span><select data-setting="${path}">${options.map(([v, t]) => `<option value="${esc(v)}" ${v === value ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select></label>`;
  }
  function pill(ok, text) {
    return `<span class="job-os-pill" data-ok="${ok ? 'true' : 'false'}">${esc(text)}</span>`;
  }
  const SECTION_ICONS = {connections: 'cloud', apify: 'radar', ai: 'ai', applicant: 'edit', apply: 'mail', scout: 'calendar',
    notifications: 'bell', resume: 'resume-studio', display: 'dashboard'};
  // Job sites Scout reads itself, with whether they still read correctly.
  function jobSitesBlock(state) {
    const sites = dashboardOf(state).site_health || [];
    if (!sites.length) return '';
    const rows = sites.map((site) => {
      const ok = site.state === 'ok';
      const checked = site.checked ? `checked ${when(site.checked)}` : 'not checked yet';
      return `<div class="site-health-row"><strong>${esc(site.name)}</strong>${pill(ok, SITE_STATE[site.state] || site.state)}<span class="site-health-when">${esc(checked)}${site.in_use ? '' : ' · no search uses it'}</span>${!ok && site.detail ? `<p class="job-os-card-note">${esc(site.detail)}</p>` : ''}</div>`;
    }).join('');
    return `<div class="job-os-conn"><div class="job-os-conn-head"><strong>Job sites</strong></div>
      <p class="job-os-card-note">Sites Scout reads itself. They are checked twice a day while a search uses them and on every run; a change in a site's pages shows here, on the Dashboard and in Scout, and is emailed once when Jobs email is on.</p>
      ${rows}<button type="button" class="job-os-btn" data-job-os-action="site-check">Check now</button></div>`;
  }
  function section(id, title, note, inner, phase) {
    return `<section class="job-os-card job-os-settings-section" id="job-os-settings-${id}">${cardHead(title, SECTION_ICONS[id], phase ? `<span class="job-os-phase" title="Saved now; takes effect when this phase ships">${esc(phase)}</span>` : '')}${note ? `<p class="job-os-card-note">${esc(note)}</p>` : ''}${inner}</section>`;
  }
  // Gmail: verified on the server with a real login, then saved to the shared
  // secrets file every profile reads. The password field is never pre-filled
  // and its value is never kept in page state.
  function gmailBlock(state, gmail, ready) {
    const msg = state.gmailMessage ? `<p class="job-os-gmail-msg" data-tone="${esc(state.gmailMessage.tone)}" role="status">${esc(state.gmailMessage.text)}</p>` : '<p class="job-os-gmail-msg" role="status"></p>';
    if (ready && !state.gmailEditing) {
      return `<div class="job-os-conn" id="job-os-gmail">
        <div class="job-os-conn-head"><strong>Gmail sender</strong>${pill(true, 'Connected')}</div>
        <p class="job-os-card-note">Hermes sends from <strong>${esc(gmail.address_hint || 'your account')}</strong>, named after the part of Hermes writing (<em>Hermes Jobs</em>, <em>Hermes Business</em>), to the <em>Send to</em> address under Notifications (this account if that is empty). ${gmail.scope === 'shared' ? 'Saved once for every profile.' : 'Saved for this profile.'}</p>
        <div class="job-os-actions"><label class="job-os-inline-select">Send test as <select id="job-os-gmail-test-context" aria-label="Sender name for the test email"><option value="jobs">Hermes Jobs</option><option value="business">Hermes Business</option></select></label><button type="button" class="job-os-btn" data-job-os-action="gmail-test">Send test email</button><button type="button" class="job-os-btn" data-job-os-action="gmail-edit">Replace</button><button type="button" class="job-os-btn job-os-btn-danger" data-job-os-action="gmail-disconnect">Disconnect</button></div>
        ${msg}
      </div>`;
    }
    return `<div class="job-os-conn" id="job-os-gmail">
      <div class="job-os-conn-head"><strong>Gmail sender</strong>${pill(false, 'Not connected')}</div>
      <p class="job-os-card-note">The account Hermes sends from. A separate Gmail just for Hermes works best; your main address goes in <em>Send to</em> under Notifications. Use a Gmail <strong>app password</strong>, not your normal password: Google Account → Security → 2-Step Verification → App passwords (<a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener noreferrer">open</a>). Hermes logs in once to check it, then saves it ${gmail.scope === 'shared' ? 'for every profile' : 'for this profile'}; it is never shown again.</p>
      <div class="job-os-grid">
        <label class="job-os-field"><span>Gmail address</span><input type="email" id="job-os-gmail-address" autocomplete="email" spellcheck="false" placeholder="you@gmail.com"></label>
        <label class="job-os-field"><span>App password</span><input type="password" id="job-os-gmail-password" autocomplete="new-password" spellcheck="false" placeholder="xxxx xxxx xxxx xxxx"></label>
      </div>
      <div class="job-os-actions"><button type="button" class="job-os-btn primary" data-job-os-action="gmail-connect">Connect Gmail</button>${ready ? '<button type="button" class="job-os-btn" data-job-os-action="gmail-cancel">Cancel</button>' : ''}</div>
      ${msg}
    </div>`;
  }
  // Apify: the token is checked with Apify, then saved in the env files like
  // Gmail's password and never shown again; the other choices are settings.
  function apifySection(state, v) {
    const ap = (state.settingsStatus || {}).apify || {};
    const msg = `<p class="job-os-gmail-msg"${state.apifyMessage ? ` data-tone="${esc(state.apifyMessage.tone)}"` : ''} role="status">${esc(state.apifyMessage ? state.apifyMessage.text : '')}</p>`;
    const where = ap.scope === 'shared' ? 'for every profile' : 'for this profile';
    const token = ap.token && !state.apifyEditing
      ? `<div class="job-os-conn" id="job-os-apify">
          <div class="job-os-conn-head"><strong>API token</strong>${pill(true, 'Connected')}</div>
          <p class="job-os-card-note">Token ending <code>${esc(ap.token_hint || '')}</code>, saved ${where}. It is never shown again.</p>
          <div class="job-os-actions"><button type="button" class="job-os-btn" data-job-os-action="apify-test">Test token</button><button type="button" class="job-os-btn" data-job-os-action="apify-edit">Replace</button><button type="button" class="job-os-btn job-os-btn-danger" data-job-os-action="apify-disconnect">Disconnect</button></div>
          ${msg}</div>`
      : `<div class="job-os-conn" id="job-os-apify">
          <div class="job-os-conn-head"><strong>API token</strong>${pill(false, 'Not connected')}</div>
          <p class="job-os-card-note">Create a free account at <a href="https://console.apify.com/sign-up" target="_blank" rel="noopener noreferrer">apify.com</a> (no card needed; $5 of usage a month), then copy your token from <a href="https://console.apify.com/settings/integrations" target="_blank" rel="noopener noreferrer">Settings → API &amp; Integrations</a>. Hermes checks it with Apify, then saves it ${where}.</p>
          <div class="job-os-grid"><label class="job-os-field"><span>Apify API token</span><input type="password" id="job-os-apify-token" autocomplete="off" spellcheck="false" placeholder="apify_api_…"></label></div>
          <div class="job-os-actions"><button type="button" class="job-os-btn primary" data-job-os-action="apify-connect">Connect Apify</button>${ap.token ? '<button type="button" class="job-os-btn" data-job-os-action="apify-cancel">Cancel</button>' : ''}</div>
          ${msg}</div>`;
    const perCity = Number(v('apify.results_per_city')) || 0;
    const cost = (0.001 + perCity * 0.0001).toFixed(3);
    return section('apify', 'Apify', 'Runs the job-site scrapers on Apify’s servers instead of this machine, so Indeed can’t block your address, LinkedIn becomes searchable, and every job arrives with its full description.', `
      ${token}
      ${toggle('apify.enabled', 'Search job sites through Apify', v('apify.enabled'), ap.token ? 'Scout searches run on Apify instead of Firecrawl; needed for LinkedIn' : 'Connect a token first')}
      <div class="job-os-grid">${(ap.sites || []).filter((site) => (site.actors || []).length).map((site) => selectField(`apify.${site.key}_actor`, `${site.name} scraper`, v(`apify.${site.key}_actor`),
        site.actors.map((a) => [a.actor, `${a.actor} — ${a.price}`]))).join('')}${numberField('apify.results_per_city', 'Results per search and city', v('apify.results_per_city'), 1, 1000, 'jobs')}</div>
      <p class="job-os-card-note apify-cost">Each job title, site and city in a search is one run, billed per job returned (prices above, free plan). With Indeed at ${perCity} results: about <strong>$${cost}</strong> a run. Scrapers that can drop off-title or already-saved jobs on their side (the title filter, LinkedIn’s valig scraper) charge only for what Scout keeps.</p>`);
  }
  function settingsView(state) {
    const s = state.settingsDraft || state.settings;
    if (!s) return LOADING;
    const status = state.settingsStatus || {};
    const fc = status.firecrawl || state.firecrawl || {};
    const gmail = status.gmail || {};
    const gmailReady = gmail.address && gmail.app_password;
    const dirty = !!state.settingsDirty;
    const v = (path) => get(s, path);
    const firecrawl = section('connections', 'Connections', '', `
      <div class="job-os-conn">
        <div class="job-os-conn-head"><strong>Firecrawl</strong>${pill(fc.state === 'healthy', FIRECRAWL_LABELS[fc.state] || 'Unknown')}</div>
        <p class="job-os-card-note">${esc(fc.detail || '')}${fc.base_url ? ` Using <code>${esc(fc.base_url)}</code>${fc.source === 'settings' ? ' (set here)' : fc.source ? ' (from your .env settings)' : ''}.` : ''}${fc.latency_ms != null ? ` ${esc(fc.latency_ms)} ms.` : ''}</p>
        ${textField('firecrawl.api_url', 'Firecrawl URL override', v('firecrawl.api_url'), 'Leave empty to use FIRECRAWL_API_URL from your .env settings', 'url')}
        <button type="button" class="job-os-btn" data-job-os-action="test-firecrawl">Test connection</button>
      </div>
      ${gmailBlock(state, gmail, gmailReady)}
      ${jobSitesBlock(state)}`);
    const ai = section('ai', 'AI', 'Used for job analysis, fit scores and resume tailoring.', `<div class="job-os-grid">
      ${textField('ai.model', 'Model', v('ai.model'))}
      ${textField('ai.provider', 'Provider', v('ai.provider'))}
      ${selectField('ai.reasoning_effort', 'Reasoning', v('ai.reasoning_effort'), [['low', 'Low'], ['medium', 'Medium'], ['high', 'High']])}</div>
      ${toggle('ai.auto_analyze', 'Analyse new finds automatically', v('ai.auto_analyze'), 'Scout queues each new job for a fit score against your resume')}`);
    const applicant = section('applicant', 'Your details', 'Used on tailored resumes and cover letters.', `<div class="job-os-grid">
      ${textField('applicant.full_name', 'Full name', v('applicant.full_name'))}
      ${textField('applicant.email', 'Email', v('applicant.email'), 'you@example.com', 'email')}
      ${textField('applicant.phone', 'Phone', v('applicant.phone'), '+1 555 0100', 'tel')}
      ${textField('applicant.location', 'Location', v('applicant.location'), 'City, Country')}
      ${textField('applicant.linkedin_url', 'LinkedIn', v('applicant.linkedin_url'), 'https://linkedin.com/in/…', 'url')}
      ${textField('applicant.portfolio_url', 'Website / portfolio', v('applicant.portfolio_url'), 'https://…', 'url')}</div>`);
    const timesMode = v('scout.schedule_mode') !== 'interval';
    const answers = section('apply', 'Application answers', 'Your standard answers to screening questions. Each job’s Apply kit uses them word for word, and Luna fits the rest to the job from your master resume. Leave a field empty to be asked to fill it in.', `<div class="scout-form-grid">
      ${textField('apply.notice_period', 'Notice period', v('apply.notice_period'), 'e.g. One month')}
      ${textField('apply.expected_salary', 'Expected salary', v('apply.expected_salary'), 'e.g. Malaysia: RM 8,000/month; Qatar: QAR 15,000/month')}
      ${textField('apply.work_authorization', 'Work authorisation', v('apply.work_authorization'), 'e.g. Malaysian citizen; needs visa sponsorship for Qatar')}
      ${textField('apply.years_experience', 'Years of experience', v('apply.years_experience'), 'e.g. 3 years in SOC operations')}
      ${textField('apply.relocation', 'Relocation', v('apply.relocation'), 'e.g. Open to relocating to Qatar')}
      ${textField('apply.languages', 'Languages', v('apply.languages'), 'e.g. English, Malay')}</div>
      <label class="job-os-field"><span>Anything else to mention</span><textarea data-setting="apply.other" rows="3" maxlength="1500" placeholder="e.g. Certifications in progress, availability for interviews">${esc(v('apply.other') || '')}</textarea></label>`);
    const scout = section('scout', 'Scout schedule', 'Job ads go up in a morning wave and an afternoon wave on weekdays (Monday to Wednesday are the busiest), so by default Scout runs just after each: 12:30 and 18:30, plus one Saturday run.', `
      ${toggle('scout.enabled', 'Run Scout automatically', v('scout.enabled'))}
      <div class="job-os-grid">${selectField('scout.schedule_mode', 'Run', v('scout.schedule_mode'), [['times', 'At set times'], ['interval', 'Every few hours']])}
        ${timesMode ? `<label class="job-os-field"><span>Times</span><input type="text" data-setting="scout.run_times" value="${esc((v('scout.run_times') || []).join(', '))}" placeholder="12:30, 18:30" autocomplete="off" spellcheck="false"></label>
        ${selectField('scout.weekend', 'Weekends', v('scout.weekend'), [['saturday', 'Saturday, first time only'], ['same', 'Same as weekdays'], ['none', 'No runs']])}
        ${textField('scout.timezone', 'Your time zone', v('scout.timezone'), 'Asia/Kuala_Lumpur')}` : numberField('scout.schedule_hours', 'Every', v('scout.schedule_hours'), 1, 168, 'hours')}
        ${numberField('scout.max_results_per_search', 'Max results per search', v('scout.max_results_per_search'), 1, 100)}</div>
      ${timesMode ? '<p class="job-os-card-note">Times are each search’s own country time and working week: Malaysia Monday to Friday, Qatar Sunday to Thursday (UTC+3). Your time zone sets the evening update under Notifications.</p>' : ''}
      ${timesMode ? toggle('scout.quiet_skip', 'Skip a run after a quiet one', v('scout.quiet_skip'), 'If a run finds 0–1 new jobs, the next run that day is skipped') : ''}
      <label class="job-os-field"><span>Never show jobs from</span><textarea data-setting="scout.blocked_companies" rows="3" placeholder="One company per line (e.g. your current employer)" spellcheck="false">${esc((v('scout.blocked_companies') || []).join('\n'))}</textarea></label>`);
    const notify = section('notifications', 'Notifications', '', `${gmailReady ? '' : '<p class="job-os-card-note">Email needs the Gmail sender: <button type="button" class="job-os-link" data-job-os-action="settings-section" data-section="connections">connect it under Connections</button>.</p>'}
      ${toggle('notifications.email_enabled', 'Email me', v('notifications.email_enabled'), gmailReady ? '' : 'Needs Gmail credentials')}
      <div class="job-os-grid">${textField('notifications.to_address', 'Send to', v('notifications.to_address'), 'you@gmail.com', 'email')}</div>
      ${toggle('notifications.notify_new_matches', 'Email good matches', v('notifications.notify_new_matches'), 'One email per update, best match first; the Scout page shows them either way')}
      <div class="job-os-grid">${numberField('notifications.min_fit_score', 'Good match from', v('notifications.min_fit_score'), 0, 100, '%')}${numberField('notifications.release_count', 'Update when this many are waiting', v('notifications.release_count'), 1, 50, 'matches')}${numberField('notifications.release_cutoff_hour', 'Or at the end of the day, at', v('notifications.release_cutoff_hour'), 0, 23, ':00')}</div>
      <p class="job-os-card-note">A good match is Luna’s fit score of your master resume against the job. 65% is a sensible bar: 75%+ is ready to apply, 65–74% has gaps that tailoring can close, and below about 60% usually misses a must-have.</p>
      ${toggle('notifications.daily_digest', 'Daily digest', v('notifications.daily_digest'))}
      <div class="job-os-grid">${numberField('notifications.digest_hour', 'Digest hour', v('notifications.digest_hour'), 0, 23, ':00')}</div>
      ${toggle('notifications.reply_actions', 'Act on replies', v('notifications.reply_actions'), 'Each job in an alert has codes; reply "TAILOR 1A2B3C4D" or "SKIP 1A2B3C4D" from the Send-to address')}
      ${notifyStatus(state.notifications)}
      <div class="job-os-conn" id="job-os-outcomes"><div class="job-os-conn-head"><strong>Employer replies</strong>${pill(gmailReady && v('notifications.track_outcomes'), gmailReady && v('notifications.track_outcomes') ? 'Reading' : 'Off')}</div>
        ${toggle('notifications.track_outcomes', 'Read employer replies', v('notifications.track_outcomes'), 'Every 10 minutes Luna reads new mail in the connected inbox (read-only) and moves an applied job to Rejected or Interview when the company and role match')}
        <p class="job-os-card-note">Employers write to the address you applied with${v('applicant.email') ? ` (<strong>${esc(v('applicant.email'))}</strong>)` : ''}. If that isn’t ${gmail.address_hint ? `<strong>${esc(gmail.address_hint)}</strong>` : 'the connected Gmail'}, add a filter there that forwards job replies to it: Gmail → Settings → Forwarding, then a filter such as <code>subject:(application OR interview OR candidate)</code> → Forward to. Each move shows on the job with the email’s subject, and can be dragged back.</p>
        ${outcomeStatus(state.notifications, gmailReady && v('notifications.track_outcomes'))}</div>`);
    const resume = section('resume', 'Resume', 'Your master resume lives in Resume Studio.', '<button type="button" class="job-os-btn" data-job-os-view="resume-studio">Open Resume Studio</button>');
    const display = section('display', 'Jobs page', '', toggle('display.show_logistics', 'Show Logistics', v('display.show_logistics'), 'The 3D view of your pipeline in the side panel'));
    const bar = `<div class="job-os-savebar" data-dirty="${dirty ? 'true' : 'false'}"><p id="job-os-settings-error" class="job-os-error" role="alert">${esc(state.settingsError || '')}</p><span class="job-os-savebar-note">${dirty ? 'Unsaved changes' : state.settingsSavedAt ? 'Saved' : ''}</span><button type="button" class="job-os-btn" data-job-os-action="discard-settings" ${dirty ? '' : 'disabled'}>Discard</button><button type="button" class="job-os-btn primary" data-job-os-action="save-settings" ${dirty ? '' : 'disabled'}>Save settings</button></div>`;
    const pages = {connections: firecrawl, apify: apifySection(state, v), scout, ai, notifications: notify, applicant, apply: answers, display: resume + display};
    const page = pages[state.settingsSection] ? state.settingsSection : 'connections';
    const apifyOn = !!((status.apify || {}).token);
    const hints = {
      connections: [gmailReady && fc.state === 'healthy', gmailReady ? (fc.state === 'healthy' ? 'All connected' : 'Gmail connected') : 'Gmail not connected'],
      apify: [apifyOn && v('apify.enabled'), apifyOn ? (v('apify.enabled') ? 'On' : 'Connected, off') : 'Not connected'],
      scout: [v('scout.enabled'), v('scout.enabled') ? 'Runs on schedule' : 'Manual runs only'],
      ai: [v('ai.auto_analyze'), v('ai.model')],
      notifications: [gmailReady && v('notifications.email_enabled'), gmailReady && v('notifications.email_enabled') ? 'Email on' : 'Email off'],
      applicant: [!!v('applicant.full_name'), v('applicant.full_name') || 'Not filled in'],
      apply: [!!v('apply.notice_period'), v('apply.notice_period') ? 'Saved' : 'Not filled in'],
      display: [null, 'Logistics, resume'],
    };
    const nav = SETTINGS_NAV.map(([group, items]) => `<p class="settings-nav-group">${group}</p>${items.map(([key, label]) => {
      const [ok, hint] = hints[key];
      return `<button type="button" class="settings-nav-item${key === page ? ' active' : ''}" data-job-os-action="settings-section" data-section="${key}"${key === page ? ' aria-current="page"' : ''}><span class="settings-nav-icon" aria-hidden="true">${icon(SECTION_ICONS[key], 16)}</span><span class="settings-nav-text"><strong>${label}</strong><small>${ok == null ? '' : `<i class="settings-nav-dot" data-ok="${ok ? 'true' : 'false'}"></i>`}<span class="settings-nav-hint">${esc(hint)}</span></small></span></button>`;
    }).join('')}`).join('');
    return `<form id="job-os-settings-form" class="job-os-settings" novalidate><div class="settings-layout"><nav class="settings-nav" aria-label="Settings sections" data-mi-tabs="y">${nav}</nav><div class="settings-page" data-page="${page}" data-key="settings-${page}">${pages[page]}</div></div>${bar}</form>`;
  }
  // Settings, grouped: what Hermes connects to, what runs on its own, and you.
  const SETTINGS_NAV = [
    ['Accounts', [['connections', 'Connections'], ['apify', 'Apify']]],
    ['Automation', [['scout', 'Scout schedule'], ['ai', 'Luna (AI)'], ['notifications', 'Notifications']]],
    ['You', [['applicant', 'Your details'], ['apply', 'Application answers']]],
    ['Page', [['display', 'Jobs page']]],
  ];
  // The Settings page a section is on (an automation row or a Scout tile asks for a section).
  const settingsPageOf = (id) => ({resume: 'display'}[id] || id || 'connections');
  const EMAIL_KINDS = {matches: 'Match alert', digest: 'Digest', reply: 'Reply', outcome: 'Employer reply'};
  function outcomeStatus(n, on) {
    const o = n && n.outcomes;
    if (!o) return '';
    return `<div class="job-os-actions"><span class="job-os-card-note">${o.checked ? `Checked ${esc(when(o.checked))}` : 'Not checked yet'}${o.error ? ` · <span class="job-os-error">${esc(o.error)}</span>` : ''}</span><button type="button" class="job-os-btn small" data-job-os-action="notify-outcomes" ${on ? '' : 'disabled'}>Check now</button></div>`;
  }
  function notifyStatus(n) {
    if (!n) return '';
    const checked = n.last_poll ? `Replies checked ${esc(when(n.last_poll))}` : 'Replies not checked yet';
    const log = (n.log || []).slice(0, 6);
    return `<div class="job-os-notify-status">
      <p class="job-os-card-note">${n.last_digest ? `Last digest ${esc(n.last_digest)}. ` : ''}${checked}.${n.last_poll_error ? ` <span class="job-os-error">${esc(n.last_poll_error)}</span>` : ''}</p>
      <div class="job-os-actions"><button type="button" class="job-os-btn" data-job-os-action="notify-digest" ${n.ready ? '' : 'disabled'}>Send digest now</button><button type="button" class="job-os-btn" data-job-os-action="notify-check" ${n.ready ? '' : 'disabled'}>Check replies now</button></div>
      ${log.length ? `<ul class="job-os-email-log">${log.map((e) => `<li data-status="${esc(e.status)}"><strong>${esc(EMAIL_KINDS[e.kind] || e.kind)}</strong> ${esc(e.status)}${e.subject ? ` · ${esc(e.subject)}` : ''}${e.detail ? `<small>${esc(e.detail)}</small>` : ''}<time>${esc(when(e.created_at))}</time></li>`).join('')}</ul>` : ''}
    </div>`;
  }
  // ---- Pipeline board -----------------------------------------------------------
  // One column per stage, from new finds to closed. Each card says where the
  // job came from (Scout's Indeed finds or the manual tracker), where it is,
  // what it pays, and the one next step for its stage.
  function cardPrimary(job) {
    const id = esc(job.id);
    const st = job.status;
    if (st === 'discovered') return job.source === 'manual'
      ? `<button type="button" class="job-os-btn small" data-job-os-action="job-form-edit" data-job-id="${id}">Add description</button>`
      : `<button type="button" class="job-os-btn small" data-job-os-action="card-details" data-job-id="${id}">Fetch details</button>`;
    if (['scraped', 'analyzed', 'shortlisted'].includes(st)) return job.has_description
      ? `<button type="button" class="job-os-btn small" data-job-os-action="card-tailor" data-job-id="${id}">Tailor resume</button>` : '';
    if (st === 'tailoring') return `<span class="pipe-busy">${statusLine(['Tailoring your resume', 'Matching the posting', 'Checking the numbers'])}</span>`;
    if (st === 'resume_ready') return `<button type="button" class="job-os-btn small" data-job-os-action="studio-open" data-job-id="${id}">Review resume</button>`;
    if (['application_ready', 'awaiting_approval', 'applying'].includes(st)) return `<button type="button" class="job-os-btn primary small" data-job-os-action="board-apply" data-job-id="${id}" data-url="${esc(job.canonical_url)}">Apply</button>`;
    return '';
  }
  // Applied for (or past it): dropping such a card on Closed asks why it closed.
  const SENT = ['submitted', 'screening', 'interviewing', 'offer', 'offer_accepted', 'offer_declined', 'rejected', 'withdrawn', 'no_response'];
  function pipeCard(job) {
    const src = sourceOf(job);
    const where = place(job);
    const work = [WORKPLACE[job.workplace], job.employment_type].filter(Boolean).join(' · ');
    // Every card has the same rows, N/A where a posting doesn't say, so all cards are one height:
    // title and score; company and site; place and when; pay and job type; one button.
    const fact = (iconName, text, label) => `<span class="pipe-fact${text ? '' : ' is-na'}" title="${esc(text ? `${label}: ${text}` : `${label} not given`)}">${icon(iconName, 14)}<span>${esc(text || 'N/A')}</span></span>`;
    const primary = cardPrimary(job) || `<button type="button" class="job-os-btn small" data-job-id="${esc(job.id)}">Open job</button>`;
    const attention = (job.attention || [])[0];
    // Pay in a card's half row: "RM 6,000 – 8,000 / month" reads as "RM 6,000–8,000/mo".
    const pay = String(job.salary_text || '').replace(/\s*[–—-]\s*/g, '–').replace(/\s*(?:\/|a|per)\s*month\b/i, '/mo')
      .replace(/\s*(?:\/|a|per)\s*year\b/i, '/yr').replace(/\s*(?:\/|an|per)\s*hour\b/i, '/hr').replace(/\s*(?:\/|a|per)\s*day\b/i, '/day');
    const stamp = job.applied ? `Applied ${when(job.applied.at)}` : when(job.updated_at);
    const status = ['closed', 'offers', 'interview'].includes(job.column) ? badge(job.status) : '';
    // A job Luna is tailoring stays put until she is done.
    const movable = job.status !== 'tailoring';
    return `<article class="pipe-card${analysing(job) ? ' is-analysing' : ''}" data-key="card-${esc(job.id)}" data-board-job="${esc(job.id)}" data-status="${esc(job.status)}" data-source="${src}" data-revision="${Number(job.revision)}" data-applied="${SENT.includes(job.status) || job.applied ? 'true' : 'false'}"${movable ? ' draggable="true"' : ''}>
      <button type="button" class="pipe-card-main" data-job-id="${esc(job.id)}">
        <span class="pipe-card-head"><strong class="pipe-card-name" title="${esc(job.title)}">${esc(job.title)}</strong>${fitRing(job.analysis, 'small')}</span>
        <span class="pipe-row"><span class="pipe-company">${esc(job.company || 'Company not set')}</span><span class="pipe-tags">${status}<span class="pipe-source" data-source="${src}">${SOURCE_LABEL[src]}</span></span></span>
        <span class="pipe-row">${fact('pin', where, 'Location')}<small class="pipe-when">${attention ? `<span class="pipe-attention" title="${esc((job.attention || []).join(' · '))}">${icon('attention', 14)}</span>` : ''}${esc(stamp)}</small></span>
        <span class="pipe-row pipe-row-split">${fact('pay', pay, 'Salary')}${fact('briefcase', work, 'Job type')}</span>
      </button>
      <div class="pipe-card-actions">${primary}</div></article>`;
  }
  // The site tab and the search box narrow what is shown; both work on what is loaded.
  function matchesQuery(job, query) {
    const q = String(query || '').trim().toLowerCase();
    if (!q) return true;
    const hay = `${job.title} ${job.company || ''} ${job.location || ''}`.toLowerCase();
    return q.split(/\s+/).every((word) => hay.includes(word));
  }
  const shownOn = (state) => (job) => (state.pipelineSource === 'all' || !state.pipelineSource || sourceOf(job) === state.pipelineSource) && matchesQuery(job, state.pipelineQuery);
  function pipelineBoard(state) {
    const board = state.board;
    if (!board) return LOADING;
    const keep = shownOn(state);
    const columns = board.columns.map((c) => Object.assign({}, c, {jobs: c.jobs.filter(keep)}));
    const total = columns.reduce((n, c) => n + c.jobs.length, 0);
    if (!total) return state.pipelineQuery ? noMatches(state) : emptyPipeline(state);
    const folded = new Set(state.collapsedColumns || []);
    const tracks = columns.map((c) => (folded.has(c.key) ? '48px' : 'minmax(272px,1fr)')).join(' ');
    const fold = (c, open) => `<button type="button" class="pipe-col-fold" data-job-os-action="pipe-collapse" data-col="${esc(c.key)}" aria-label="${open ? 'Collapse' : 'Expand'} ${esc(c.label)}" title="${open ? 'Collapse' : 'Expand'}" aria-expanded="${open}">${icon(open ? 'prev' : 'next', 14)}</button>`;
    return `<div class="pipe-board" role="list" aria-label="Pipeline stages" style="grid-template-columns:${tracks}">${columns.map((c) => (folded.has(c.key)
      ? `<section class="pipe-col is-folded" data-key="col-${esc(c.key)}" data-col="${esc(c.key)}" role="listitem" aria-label="${esc(c.label)}, collapsed"><header class="pipe-col-head">${fold(c, false)}<span class="job-os-count">${c.jobs.length}</span><span class="pipe-col-dot" aria-hidden="true"></span><h3>${esc(c.label)}</h3></header><div class="pipe-col-cards"></div></section>`
      : `<section class="pipe-col" data-key="col-${esc(c.key)}" data-col="${esc(c.key)}" role="listitem" aria-label="${esc(c.label)}"><header class="pipe-col-head"><span class="pipe-col-dot" aria-hidden="true"></span><h3>${esc(c.label)}</h3><span class="job-os-count">${c.jobs.length}</span>${fold(c, true)}</header><div class="pipe-col-cards">${c.jobs.map((j) => pipeCard(Object.assign({column: c.key}, j))).join('') || '<p class="pipe-empty">Drop a job here</p>'}</div></section>`)).join('')}</div>
      <div class="pipe-hscroll" aria-hidden="true"><div class="pipe-hscroll-track"></div></div>`;
  }
  function noMatches(state) {
    return `<section class="job-os-card job-os-empty pipe-empty-state"><strong>No jobs match “${esc(state.pipelineQuery.trim())}”</strong><p>Search looks at each job’s title, company and place${state.pipelineSource !== 'all' ? ` on the ${esc(SOURCE_LABEL[state.pipelineSource] || state.pipelineSource)} tab` : ''}.</p><div class="job-os-actions"><button type="button" class="job-os-btn" data-job-os-action="pipe-search-clear">Clear search</button></div></section>`;
  }
  function emptyPipeline(state) {
    const src = state.pipelineSource;
    const site = src !== 'all' && src !== 'manual' ? SOURCE_LABEL[src] : '';
    const title = src === 'manual' ? 'No tracked jobs yet' : site ? `No ${site} finds yet` : 'Your pipeline is empty';
    const body = src === 'manual' ? 'Add a job you found yourself — paste its link and description, then score and tailor your resume for it.'
      : site ? `Create a Scout search that includes ${site}${src !== 'indeed' ? ' (through Apify)' : ''}; every posting it finds lands here.`
        : `Scout fills it from ${SITES.map(([, n]) => n).join(' and ')}, or add a job you found yourself.`;
    const actions = [src !== 'manual' ? '<button type="button" class="job-os-btn" data-job-os-view="scout">Open Scout</button>' : '',
      !site ? `<button type="button" class="job-os-btn primary" data-job-os-action="job-form-new">${icon('import', 14)}Add job</button>` : ''].join('');
    return `<section class="job-os-card job-os-empty pipe-empty-state"><strong>${title}</strong><p>${body}</p><div class="job-os-actions">${actions}</div></section>`;
  }
  // ---- Job drawer: details, actions, notes -----------------------------------------
  const EVENT_TEXT = {job_created: 'Saved', application_submitted: 'Applied', details_edited: 'Details edited'};
  function activity(state) {
    const items = (state.jobTimeline || []).slice().reverse().filter((e) => e.type === 'note' || e.type === 'status_changed' || EVENT_TEXT[e.type]);
    const rows = items.slice(0, 30).map((e) => {
      const why = e.data.by === 'email' ? ` · from an email${e.data.subject ? `: “${esc(e.data.subject)}”` : ''}${e.data.summary ? ` — ${esc(e.data.summary)}` : ''}`
        : e.data.by === 'scout' ? ' · title off target' : '';
      const text = e.type === 'note' ? esc(e.data.text) : e.type === 'status_changed' ? `Moved to <strong>${esc(statusLabel(e.data.to))}</strong>${why}` : esc(EVENT_TEXT[e.type]);
      return `<li data-kind="${e.type === 'note' ? 'note' : 'event'}"><span>${text}</span><time>${esc(when(e.at))}</time></li>`;
    }).join('');
    return `<section class="job-drawer-section"><h3>Notes &amp; activity</h3>
      <form id="job-os-note-form" class="job-note-form"><textarea name="text" rows="2" maxlength="2000" placeholder="Add a note — a recruiter call, a referral, a follow-up date"></textarea><button type="submit" class="job-os-btn">Add note</button></form>
      ${rows ? `<ul class="job-activity">${rows}</ul>` : ''}</section>`;
  }
  // Apply kit: everything to apply by hand in a minute or two. Hermes never
  // submits applications itself (the sites forbid it); you paste and send.
  const APPLYING = ['discovered', 'scraped', 'analyzed', 'shortlisted', 'tailoring', 'resume_ready', 'application_ready', 'awaiting_approval', 'applying'];
  function applyKitPanel(job) {
    if (!APPLYING.includes(job.status)) return '';
    const docs = job.documents || {};
    const resumeDoc = docs.resume && ['ready', 'needs_review'].includes(docs.resume.status) ? docs.resume : null;
    const letterDoc = docs.cover_letter && ['ready', 'needs_review'].includes(docs.cover_letter.status) ? docs.cover_letter : null;
    const exp = (doc, fmt) => `/api/job-os/documents/${encodeURIComponent(doc.id)}/export?format=${fmt}`;
    const files = resumeDoc
      ? `<div class="job-os-actions"><a class="job-os-btn small" href="${exp(resumeDoc, 'docx')}">Resume DOCX</a><a class="job-os-btn small" href="${exp(resumeDoc, 'pdf')}" target="_blank" rel="noopener">Resume PDF</a>${letterDoc ? `<a class="job-os-btn small" href="${exp(letterDoc, 'docx')}">Cover letter DOCX</a>` : ''}<button type="button" class="job-os-btn small" data-job-os-action="studio-open" data-job-id="${esc(job.id)}">Open in Resume Studio</button></div>${resumeDoc.status === 'needs_review' ? '<p class="board-attention">The tailored resume has numbers to check before sending.</p>' : ''}`
      : job.status === 'tailoring' ? '<p class="job-os-card-note">Luna is tailoring your resume…</p>'
        : `<p class="job-os-card-note">No tailored resume yet — your master resume works, but a tailored one scores better.</p>${job.description ? `<button type="button" class="job-os-btn small" data-job-os-action="job-tailor">Tailor resume</button>` : ''}`;
    const kit = job.apply_kit;
    let answers;
    if (!kit) answers = `<p class="job-os-card-note">Luna writes ready-to-paste answers to the usual screening questions from this job, your master resume and your <button type="button" class="job-os-link" data-job-os-view="settings">application answers</button>.</p>${job.description ? '<button type="button" class="job-os-btn small primary" data-job-os-action="apply-kit">Prepare answers</button>' : ''}`;
    else if (kit.status === 'running') answers = writingPanel('Luna is writing your answers…');
    else if (kit.status === 'failed') answers = `<p class="job-os-error">${esc(kit.error || 'Preparing the answers failed.')}</p><button type="button" class="job-os-btn small" data-job-os-action="apply-kit">Try again</button>`;
    else answers = `<ol class="apply-answers">${kit.answers.map((a) => `<li${/^Not provided/.test(a.answer) ? ' data-missing="true"' : ''}><strong>${esc(a.question)}</strong><p>${esc(a.answer)}</p><button type="button" class="job-os-btn small" data-copy-text="${esc(a.answer)}">Copy</button></li>`).join('')}</ol>
      <button type="button" class="job-os-btn small" data-job-os-action="apply-kit">Prepare again</button>`;
    return `<section class="job-drawer-section apply-kit"><h3>Apply kit</h3>
      <div class="apply-step"><span class="apply-step-n">1</span><div><h4>Documents</h4>${files}</div></div>
      <div class="apply-step"><span class="apply-step-n">2</span><div><h4>Screening answers</h4>${answers}</div></div>
      <div class="apply-step"><span class="apply-step-n">3</span><div><h4>Apply on the site</h4><p class="job-os-card-note">Open the posting, paste, send — then record it here.</p>
        <div class="job-os-actions"><a class="job-os-btn small primary" href="${esc(job.canonical_url)}" target="_blank" rel="noopener noreferrer">${icon('external', 14)}Open posting</a><button type="button" class="job-os-btn small" data-job-os-action="board-apply" data-job-id="${esc(job.id)}" data-url="${esc(job.canonical_url)}">I’ve applied</button></div></div></div></section>`;
  }
  function jobDrawer(state) {
    const job = state.jobDetail;
    if (!job) return '';
    const src = sourceOf(job);
    const where = place(job);
    const meta = [job.company, where].filter(Boolean).map(esc).join(' · ');
    return `<div class="job-drawer-backdrop" data-job-os-action="job-close"></div>
      <aside class="job-drawer" id="job-os-detail" role="dialog" aria-label="${esc(job.title)}">
        <header class="job-drawer-head"><div class="job-drawer-title"><div class="job-drawer-tags">${badge(job.status)}<span class="pipe-source" data-source="${src}">${SOURCE_LABEL[src]}</span></div><h2>${esc(job.title)}</h2>${meta ? `<p>${meta}</p>` : ''}</div>
          <button type="button" class="wh-insp-close job-os-detail-close" data-job-os-action="job-close" aria-label="Close details">×</button></header>
        <div class="job-drawer-body">
          ${jobChips(job)}
          <div class="job-os-actions">${detailActions(job)}<a class="job-os-btn" href="${esc(job.canonical_url)}" target="_blank" rel="noopener noreferrer">${icon('external', 14)}Open posting</a><button type="button" class="job-os-btn" data-job-os-action="job-form-edit" data-job-id="${esc(job.id)}">${icon('edit', 14)}Edit</button></div>
          ${job.status === 'tailoring' ? writingPanel('Luna is tailoring your resume and cover letter for this job…') : ''}
          ${interviewPanel(job)}
          ${analysisPanel(job)}
          ${applyKitPanel(job)}
          ${job.description ? `<details class="job-os-desc-wrap"${job.analysis && job.analysis.status === 'done' ? '' : ' open'}><summary>Job description</summary><div class="job-os-description">${esc(job.description)}</div></details>`
            : `<p class="job-os-card-note">No description yet. ${src === 'manual' ? 'Edit the job and paste it in to' : 'Fetch details to'} score and tailor your resume for it.</p>`}
          ${activity(state)}
        </div></aside>`;
  }
  // ---- Job form: the manual tracker (add) and editing any job ---------------------------
  const EMPLOYMENT = ['Full time', 'Part time', 'Contract', 'Internship', 'Temporary'];
  function jobForm(state) {
    const f = state.jobForm;
    if (!f) return '';
    const editing = !!f.id;
    const field = (name, label, attrs, wide) => `<label class="job-os-field${wide ? ' wide' : ''}"><span>${label}</span><input name="${name}" value="${esc(f[name])}" ${attrs || ''}></label>`;
    const options = (values, current, blank) => `<option value="">${blank}</option>${values.map(([v, l]) => `<option value="${esc(v)}" ${v === current ? 'selected' : ''}>${esc(l)}</option>`).join('')}`;
    const countries = (state.countries || []).map((c) => `<option value="${esc(c.name)}"></option>`).join('');
    return `<div class="job-drawer-backdrop" data-job-os-action="job-form-close"></div>
      <aside class="job-drawer job-form-drawer" role="dialog" aria-label="${editing ? 'Edit job' : 'Add a job'}">
        <header class="job-drawer-head"><div class="job-drawer-title"><h2>${editing ? 'Edit job' : 'Add a job'}</h2><p>${editing ? 'Correct the details or paste in the description.' : 'Track a job you found yourself. With its description, Luna can score your resume against it and tailor one for it.'}</p></div>
          <button type="button" class="wh-insp-close" data-job-os-action="job-form-close" aria-label="Close">×</button></header>
        <form id="job-os-job-form" class="job-drawer-body job-form" novalidate>
          <div class="job-form-grid">
            ${field('title', 'Job title <em>required</em>', 'required maxlength="240" placeholder="e.g. Data Analyst"', true)}
            ${field('company', 'Company', 'maxlength="240"')}
            ${field('canonical_url', 'Job link <em>required</em>', `type="url" required placeholder="https://" ${editing ? 'disabled' : ''}`)}
            ${field('country', 'Country', 'list="job-os-countries" maxlength="80" placeholder="e.g. Malaysia"')}
            ${field('location', 'City', 'maxlength="240" placeholder="e.g. Kuala Lumpur"')}
            ${field('salary_text', 'Salary', 'maxlength="120" placeholder="e.g. RM 6,000 – 8,000 / month"')}
            <label class="job-os-field"><span>Employment type</span><select name="employment_type">${options(EMPLOYMENT.map((e) => [e, e]), f.employment_type, 'Not set')}</select></label>
            <label class="job-os-field"><span>Workplace</span><select name="workplace">${options([['onsite', 'On-site'], ['hybrid', 'Hybrid'], ['remote', 'Remote']], f.workplace, 'Not set')}</select></label>
            ${editing ? '' : `<label class="job-os-field"><span>Stage</span><select name="stage"><option value="saved" ${f.stage !== 'applied' ? 'selected' : ''}>Saved — not applied yet</option><option value="applied" ${f.stage === 'applied' ? 'selected' : ''}>Already applied</option></select></label>`}
            <label class="job-os-field wide"><span>Job description</span><textarea name="description" rows="9" maxlength="20000" placeholder="Paste the full job description">${esc(f.description)}</textarea></label>
            ${editing ? '' : `<label class="job-os-field wide"><span>Note</span><textarea name="note" rows="2" maxlength="2000" placeholder="Optional — who referred you, where you found it">${esc(f.note)}</textarea></label>`}
          </div>
          <datalist id="job-os-countries">${countries}</datalist>
          <p class="job-os-error" role="alert">${esc(state.jobFormError || '')}</p>
          <div class="job-form-actions"><button type="button" class="job-os-btn" data-job-os-action="job-form-close">Cancel</button><button type="submit" class="job-os-btn primary">${editing ? 'Save changes' : 'Save job'}</button></div>
        </form></aside>`;
  }
  // Apify bills per job: this month's spend against the account's limit, in
  // the side panel like the chat page's usage meter (cells show what is left),
  // warning from 80% so scheduled runs don't stop by surprise.
  function apifyWidget(info) {
    const u = info && info.usage;
    if (!u || !u.limit_usd) return '';
    const left = Math.max(0, u.limit_usd - u.used_usd);
    const remaining = Math.max(0, Math.min(100, Math.round(100 * left / u.limit_usd)));
    const filled = Math.round(remaining / 10);
    const level = remaining <= 5 ? 'danger' : u.warn || remaining <= 20 ? 'warn' : 'normal';
    const cells = Array.from({length: 10}, (_, i) => `<span class="chat-usage-widget-battery-cell${i < filled ? ' is-filled' : ''}" style="--usage-battery-index:${i}"></span>`).join('');
    return `<section class="chat-usage-widget job-os-apify-widget${u.warn ? ' is-warn' : ''}" aria-label="Apify credit">
      <div class="chat-usage-widget-row chat-usage-widget-title-row"><span class="chat-usage-widget-label"><span class="chat-usage-widget-label-stage">Apify credit</span></span><a class="job-os-apify-link" href="https://console.apify.com/billing" target="_blank" rel="noopener noreferrer" title="Open Apify billing" aria-label="Open Apify billing">${icon('external', 14)}</a></div>
      <div class="chat-usage-widget-battery" data-level="${level}" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${remaining}" aria-label="${remaining}% of the Apify credit left">${cells}</div>
      <div class="chat-usage-widget-meta"><span class="chat-usage-widget-plan">$${left.toFixed(2)} left of $${u.limit_usd.toFixed(2)}</span><span class="chat-usage-widget-percent">${remaining}%</span></div>
      <div class="chat-usage-widget-reset">${u.warn ? 'Low: scheduled runs stop when it runs out' : `$${u.used_usd.toFixed(2)} used${u.cycle_end ? ` · resets after ${esc(u.cycle_end)}` : ''}`}</div></section>`;
  }
  // Activity calendars under the funnel: one month at a time, a cell per day,
  // coloured by what happened that day on your clock.
  const pad2 = (n) => String(n).padStart(2, '0');
  const CALENDARS = [
    {key: 'found', title: 'Jobs found', icon: 'radar', count: (d) => d.found || 0,
      level: (n) => (n >= 30 ? 4 : n >= 10 ? 3 : n >= 3 ? 2 : n ? 1 : 0), tip: (n) => `${n} found`},
    {key: 'applied', title: 'Applications', icon: 'applications', count: (d) => d.applied || 0,
      level: (n) => (n >= 4 ? 4 : n >= 3 ? 3 : n >= 2 ? 2 : n ? 1 : 0), tip: (n) => `${n} sent`},
    {key: 'replies', title: 'Replies', icon: 'mail', count: (d) => (d.interview || 0) + (d.rejected || 0),
      tone: (d) => (d.interview && d.rejected ? 'mixed' : d.interview ? 'good' : d.rejected ? 'bad' : ''),
      tip: (n, d) => [d.interview && `${d.interview} interview${d.interview === 1 ? '' : 's'}`, d.rejected && `${d.rejected} rejection${d.rejected === 1 ? '' : 's'}`].filter(Boolean).join(', ')},
  ];
  function activityCalendars(activity, back) {
    if (!activity || !activity.today) return '';
    const [ty, tm] = activity.today.split('-').map(Number);
    const first = new Date(ty, tm - 1 - (back || 0), 1);
    const year = first.getFullYear();
    const month = first.getMonth();
    const length = new Date(year, month + 1, 0).getDate();
    const lead = (first.getDay() + 6) % 7; // Monday first
    const dayKey = (day) => `${year}-${pad2(month + 1)}-${pad2(day)}`;
    const data = (day) => (activity.days || {})[dayKey(day)] || {};
    const monthName = first.toLocaleDateString(undefined, {month: 'long', year: 'numeric'});
    const heads = ['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((d) => `<span class="cal-dow">${d}</span>`).join('');
    const cals = CALENDARS.map((cal) => {
      let total = 0;
      let interviews = 0;
      let rejections = 0;
      const cells = Array.from({length: lead}, () => '<span class="cal-day is-blank"></span>').concat(Array.from({length: length}, (_, i) => {
        const day = i + 1;
        const d = data(day);
        const n = cal.count(d);
        total += n; interviews += d.interview || 0; rejections += d.rejected || 0;
        const today = dayKey(day) === activity.today;
        const future = dayKey(day) > activity.today;
        const label = `${first.toLocaleDateString(undefined, {month: 'short'})} ${day}${n ? `: ${cal.tip(n, d)}` : ''}`;
        return `<span class="cal-day${today ? ' is-today' : ''}${future ? ' is-future' : ''}"${n ? ` data-level="${cal.level ? cal.level(n) : 1}"${cal.tone ? ` data-tone="${cal.tone(d)}"` : ''}` : ''} title="${esc(label)}">${day}</span>`;
      })).join('');
      // Days in a row up to today with at least one application (this month only).
      let streak = 0;
      if (cal.key === 'applied' && !back) for (let day = Number(activity.today.slice(8)); day >= 1 && cal.count(data(day)); day -= 1) streak += 1;
      const stat = cal.key === 'replies'
        ? `<span><i class="cal-key" data-tone="good"></i>${interviews} interview${interviews === 1 ? '' : 's'}</span><span><i class="cal-key" data-tone="bad"></i>${rejections} rejected</span>`
        : cal.key === 'applied' ? `<span><strong>${total}</strong> sent</span><span>Streak <strong>${streak}</strong> day${streak === 1 ? '' : 's'}</span>`
          : `<span><strong>${total}</strong> this month</span>`;
      return `<div class="cal" data-cal="${cal.key}"><div class="cal-head"><span class="cal-title"><span class="cal-icon" aria-hidden="true">${icon(cal.icon, 14)}</span>${cal.title}</span></div><div class="cal-grid" role="img" aria-label="${esc(`${cal.title}, ${monthName}: ${total}`)}">${heads}${cells}</div><div class="cal-stat">${stat}</div></div>`;
    }).join('');
    const step = (dir, label, iconName, disabled) => `<button type="button" class="job-os-icon-btn small" data-job-os-action="activity-month" data-step="${dir}" aria-label="${label}" title="${label}" ${disabled ? 'disabled' : ''}>${icon(iconName, 14)}</button>`;
    return `<div class="activity"><div class="activity-head"><h3>Activity</h3><span class="activity-month">${step(1, 'Previous month', 'prev', back >= 5)}<span>${esc(monthName)}</span>${step(-1, 'Next month', 'next', !back)}</span></div><div class="cals">${cals}</div></div>`;
  }
  function funnelCard(funnel, activity, back) {
    const rows = funnel && funnel.length && funnel[0].count ? funnel : null;
    const max = rows ? Math.max(...rows.map((st) => st.count), 1) : 1;
    const body = rows
      ? `<div class="funnel">${rows.map((st, i) => `<div class="funnel-row"><span>${esc(st.label)}</span><div class="funnel-track"><i style="--w:${Math.max(2, Math.round(100 * st.count / max))}%;--i:${i}"></i></div><strong data-count-key="funnel-${esc(st.key)}">${st.count}</strong></div>`).join('')}</div>`
      : '<p class="job-os-card-note card-empty-note">Your funnel fills in as Scout finds jobs and you move them along.</p>';
    return `<section class="job-os-card funnel-card">${cardHead('Your funnel', 'chart')}${body}${activityCalendars(activity, back)}</section>`;
  }
  // ---- Pipeline toolbar ------------------------------------------------------
  function sortJobs(jobs, by) {
    if (by !== 'fit') return jobs;
    const score = (j) => (j.analysis && j.analysis.fit_score != null ? j.analysis.fit_score : -1);
    return jobs.slice().sort((a, b) => score(b) - score(a));
  }
  function pipelineBar(state, jobs, counts) {
    const unanalysed = jobs.filter((j) => j.status === 'scraped' && j.has_description && !j.analysis).length;
    const busy = jobs.filter(analysing).length;
    const tabs = [['all', 'All'], ...SITES, ['manual', 'Manual']].map(([key, text]) => {
      const on = state.pipelineSource === key;
      return `<button type="button" role="tab" aria-selected="${on}" class="seg-btn${on ? ' active' : ''}" data-job-os-action="pipe-source" data-source="${key}">${text}<span class="seg-count">${Number(counts[key] || 0)}</span></button>`;
    }).join('');
    const modes = [['board', 'Board'], ['list', 'List']].map(([key, text]) => {
      const on = state.pipelineMode === key;
      return `<button type="button" class="seg-btn icon${on ? ' active' : ''}" aria-pressed="${on}" data-job-os-action="pipe-mode" data-mode="${key}" title="${text}">${icon(key, 15)}<span class="sr-only">${text}</span></button>`;
    }).join('');
    const sort = state.pipelineMode === 'list' ? `<label class="job-os-inline-select">Sort <select id="job-os-sort" aria-label="Sort jobs"><option value="newest" ${state.sortBy === 'newest' ? 'selected' : ''}>Newest</option><option value="fit" ${state.sortBy === 'fit' ? 'selected' : ''}>Best match</option></select></label>` : '';
    const query = state.pipelineQuery || '';
    const search = `<label class="pipe-search${query ? ' has-query' : ''}"><span class="sr-only">Search jobs</span>${icon('scout', 16)}<input type="search" id="job-os-pipe-search" value="${esc(query)}" placeholder="Search jobs" autocomplete="off" spellcheck="false" aria-label="Search jobs by title or company"><kbd aria-hidden="true">/</kbd>${query ? `<button type="button" class="pipe-search-clear" data-job-os-action="pipe-search-clear" aria-label="Clear search" title="Clear (Esc)">${icon('close', 16)}</button>` : ''}</label>`;
    return `<div class="pipe-toolbar"><div class="seg" role="tablist" aria-label="Where jobs came from" data-mi-tabs>${tabs}</div><div class="seg" role="group" aria-label="Layout" data-mi-tabs>${modes}</div>${search}${sort}${busy ? statusLine([`Scoring ${busy} job${busy === 1 ? '' : 's'}…`, 'Reading postings…'], 'analysing-chip') : ''}<span class="scout-bar-spacer"></span>${unanalysed ? `<button type="button" class="job-os-btn" data-job-os-action="analyze-new">Score ${unanalysed} new</button>` : ''}<button type="button" class="job-os-btn primary pipe-add-btn" data-job-os-action="job-form-new" aria-label="Add job" title="Add job">${icon('import', 20)}</button></div>`;
  }
  // ---- Scout ------------------------------------------------------------
  const RUN_LABELS = {queued: 'Starting', searching: 'Searching job sites', scraping: 'Reading postings', completed: 'Finished',
    cancelled: 'Cancelled', failed: 'Failed', interrupted: 'Interrupted'};
  const ACTIVE_RUN = ['queued', 'searching', 'scraping'];
  const latestRun = (state, searchId) => (state.runs || []).find((run) => run.search_id === searchId) || null;
  function until(epoch) {
    const s = Math.round(Number(epoch || 0) - Date.now() / 1000);
    if (!epoch) return '';
    if (s <= 60) return 'any minute';
    if (s < 3600) return `in ${Math.round(s / 60)}m`;
    return `in ${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m`;
  }
  // The run body is the only part repainted while polling, so the radar keeps spinning.
  function runBody(run) {
    const c = run.counts || {};
    const active = ACTIVE_RUN.includes(run.status);
    const stats = [['found', 'Found'], ['scraped', 'Read'], ['saved', 'New'], ['duplicates', 'Known'], ['filtered', 'Skipped'], ['closed', 'Closed']]
      .map(([key, label]) => `<span class="scout-stat${key === 'saved' && c.saved ? ' is-new' : ''}"><strong data-count-key="scout-${esc(run.id)}-${key}">${Number(c[key] || 0)}</strong>${label}</span>`).join('');
    const blocked = c.blocked ? `<span class="scout-stat"><strong>${Number(c.blocked)}</strong>Blocked</span>` : '';
    const errors = c.errors ? `<span class="scout-stat is-error"><strong>${Number(c.errors)}</strong>Errors</span>` : '';
    return `<div class="scout-run-head"><span class="scout-run-state" data-status="${esc(run.status)}">${active ? statusLine([RUN_LABELS[run.status] || run.status]) : esc(RUN_LABELS[run.status] || run.status)}</span><span class="scout-run-detail" title="${esc(run.stage_detail || '')}">${esc(run.stage_detail || '')}</span>${active ? `<button type="button" class="job-os-btn small" data-job-os-action="scout-cancel" data-run-id="${esc(run.id)}">Cancel</button>` : `<small>${esc(when(run.finished_at || run.created_at))}</small>`}</div><div class="scout-stats">${stats}${blocked}${errors}</div>`;
  }
  function runPanel(run, search) {
    if (!run) {
      // Same outline as a run, so every search card keeps one shape.
      const hint = search && search.last_run_at ? `Last ran ${esc(when(search.last_run_at))}; its results have been cleared.` : 'Run it now, or it runs at the next scheduled time.';
      return `<div class="scout-run is-empty"><span class="scout-run-idle" aria-hidden="true">${icon('clock', 18)}</span><div class="scout-run-body"><div class="scout-run-head"><span class="scout-run-state">Not run yet</span></div><span class="scout-run-detail">${hint}</span></div></div>`;
    }
    const active = ACTIVE_RUN.includes(run.status);
    return `<div class="scout-run${active ? ' is-active' : ''}" data-run-panel="${esc(run.id)}" data-status="${esc(run.status)}">${active ? '<span class="scout-radar" aria-hidden="true"><i></i><i></i><i></i></span>' : ''}<div class="scout-run-body" aria-live="polite">${runBody(run)}</div></div>`;
  }
  function searchCard(search, state) {
    const run = latestRun(state, search.id);
    const active = run && ACTIVE_RUN.includes(run.status);
    const viaApify = !!(state.apify && state.apify.active);
    // remote.id is read directly, so a search with it can always run.
    const ready = viaApify || (state.firecrawl && state.firecrawl.state === 'healthy') || [...SITE_DIRECT].some((s) => (search.sites || []).includes(s));
    const schedOn = state.schedule && state.schedule.enabled;
    const schedule = !search.enabled ? 'Paused' : !schedOn ? 'Schedule off' : search.next_run_at ? `Next ${until(search.next_run_at)}` : 'Scheduled';
    const fact = (label, value, muted) => `<div><dt>${label}</dt><dd${muted ? ' class="is-muted"' : ''}>${value}</dd></div>`;
    const broken = Object.fromEntries(siteProblems(state).map((site) => [site.site, site]));
    const sites = (search.sites || ['indeed']).map((k) => broken[k]
      ? `<span class="pipe-source is-broken" data-source="${esc(k)}" title="${esc(broken[k].name)}: ${esc(SITE_STATE[broken[k].state] || '')}">${icon('close', 12)}${esc(SOURCE_LABEL[k] || k)}</span>`
      : `<span class="pipe-source" data-source="${esc(k)}">${esc(SOURCE_LABEL[k] || k)}</span>`).join('');
    const host = (state.countries || []).find((c) => c.code === search.country);
    return `<article class="job-os-card scout-search${search.enabled ? '' : ' is-off'}" data-key="search-${esc(search.id)}" data-search-id="${esc(search.id)}">
      <div class="scout-search-head"><span class="card-icon" aria-hidden="true">${icon('radar', 16)}</span><div class="scout-search-title"><h3 title="${esc(search.name)}">${esc(search.name)}</h3><p title="${esc(search.keywords)}">${esc(search.keywords)}</p></div>
        <label class="job-os-toggle compact" title="${search.enabled ? 'Included in scheduled runs' : 'Paused'}"><input type="checkbox" data-job-os-action="scout-toggle" data-search-id="${esc(search.id)}" ${search.enabled ? 'checked' : ''}><span class="job-os-toggle-track" aria-hidden="true"></span><span class="sr-only">Enabled</span></label></div>
      <dl class="scout-facts">
        ${fact('Sites', `<span class="job-os-chips">${sites}</span>`)}
        ${fact('Country', search.country_name ? `${icon('pin', 14)}<span title="Searched on ${esc(host ? host.host : 'Indeed')}">${esc(search.country_name)}</span>` : 'Choose a country', !search.country_name)}
        ${fact('Cities', (search.locations || []).length ? esc(search.locations.join(', ')) : 'Whole country', !(search.locations || []).length)}
        ${fact('Posted', esc(POSTED[search.posted_within_days] || 'Any time') + (search.remote_only ? ' · Remote only' : ''))}
        ${fact('Titles', search.strict_titles === false ? 'Any title' : `<span title="${esc((search.related_titles || []).join(', ') || 'Luna adds related titles on the next run')}">Yours${(search.related_titles || []).length ? ` + ${search.related_titles.length} related` : ' only'}</span>`, search.strict_titles === false)}
        ${fact('Schedule', esc(schedule), !search.enabled || !schedOn)}
      </dl>
      ${runPanel(run, search)}
      ${search.off_target ? `<div class="scout-tidy" role="status"><span>${icon('attention', 16)}<span><strong>${Number(search.off_target)}</strong> saved find${search.off_target === 1 ? '' : 's'} don’t match these titles</span></span><button type="button" class="job-os-btn small" data-job-os-action="scout-tidy" data-search-id="${esc(search.id)}">Move to Closed</button></div>` : ''}
      <div class="scout-search-actions"><button type="button" class="job-os-btn primary" data-job-os-action="scout-run" data-search-id="${esc(search.id)}" ${active || !ready ? 'disabled' : ''} title="${ready ? (viaApify ? 'Runs on Apify' : '') : 'Firecrawl is not ready — see Settings, or turn on Apify'}">${icon('flash', 16)}${active ? 'Running…' : 'Run now'}</button><button type="button" class="job-os-icon-btn" data-job-os-action="scout-edit" data-search-id="${esc(search.id)}" aria-label="Edit search" title="Edit search">${icon('edit', 16)}</button><button type="button" class="job-os-icon-btn danger" data-job-os-action="scout-delete" data-search-id="${esc(search.id)}" aria-label="Delete search" title="Delete search">${icon('trash', 16)}</button></div>
    </article>`;
  }
  const POSTED = {1: 'Last 24 hours', 3: 'Last 3 days', 7: 'Last 7 days', 14: 'Last 14 days'};
  function searchFormCard(form, state) {
    if (!form) return '';
    const editing = !!form.id;
    const countries = (state.countries || []).map((c) => `<option value="${esc(c.code)}" ${c.code === form.country ? 'selected' : ''}>${esc(c.name)}</option>`).join('');
    const posted = (state.postedWithin || [0, 1, 3, 7, 14]).map((d) => `<option value="${d}" ${Number(form.posted_within_days) === d ? 'selected' : ''}>${esc(POSTED[d] || 'Any time')}</option>`).join('');
    const host = ((state.countries || []).find((c) => c.code === form.country) || {}).host;
    const apifyOn = !!(state.apify && state.apify.active);
    return `<section class="job-os-card scout-form" id="scout-form"><div class="job-os-card-head"><div><h2>${editing ? 'Edit search' : 'New search'}</h2><p class="job-os-card-note">Scout searches each job site for these titles in each city${host ? ` (Indeed: <code>${esc(host)}</code>)` : ''} and saves every posting it finds.</p></div></div>
      <form id="job-os-search-form" novalidate><div class="scout-form-grid">
        <label class="job-os-field wide"><span>Job titles <em>required</em></span><input name="keywords" required maxlength="200" placeholder="e.g. SOC Analyst, IT Analyst, Security Analyst" value="${esc(form.keywords)}"><small class="job-os-field-hint">Comma-separated; each title is searched on its own (up to 5).</small></label>
        <label class="job-os-toggle wide"><input type="checkbox" name="strict_titles" ${form.strict_titles !== false ? 'checked' : ''}><span class="job-os-toggle-track" aria-hidden="true"></span><span class="job-os-toggle-text"><strong>Only keep matching titles</strong><small>Job sites return loose matches (sales roles for “IT Analyst”). Keep a job only when its title matches one of yours or a related title below.</small></span></label>
        <label class="job-os-field wide"><span>Related titles</span><span class="field-with-action"><input name="related_titles" maxlength="900" placeholder="e.g. Threat Intelligence Analyst, Incident Response Analyst" value="${esc(form.related_titles || '')}"><button type="button" class="job-os-btn small" data-job-os-action="scout-suggest">${icon('magic', 14)}Suggest</button></span><small class="job-os-field-hint">Comma-separated, up to 15. Left empty, Luna fills it in on the next run; edit it any time.</small></label>
        <label class="job-os-field wide"><span>Title must contain</span><input name="title_filter" maxlength="300" placeholder="e.g. analyst — or: soc, security analyst" value="${esc(form.title_filter)}"><small class="job-os-field-hint">Keeps a job only if its title has all the words of at least one phrase (comma-separated). Job sites match loosely, so this cuts the noise. Empty = keep everything.</small></label>
        <label class="job-os-field"><span>Country <em>required</em></span><select name="country" required data-job-os-change="scout-country"><option value="">Choose…</option>${countries}</select></label>
        <label class="job-os-field"><span>Cities</span><input name="locations" placeholder="Comma-separated, e.g. Kuala Lumpur, Penang. Empty = whole country" value="${esc(form.locations)}"></label>
        <label class="job-os-field"><span>Date posted</span><select name="posted_within_days">${posted}</select></label>
        <label class="job-os-field"><span>Name</span><input name="name" maxlength="80" placeholder="Defaults to the keywords" value="${esc(form.name)}"></label>
        <fieldset class="job-os-field wide scout-sites"><legend>Job sites</legend><div class="scout-site-options">${SITES.map(([key, text]) => {
          const covered = !SITE_COUNTRIES[key] || !form.country || SITE_COUNTRIES[key].includes(form.country);
          const direct = SITE_DIRECT.has(key);
          const note = !covered ? 'not in this country' : direct ? 'remote jobs, read directly' : key === 'indeed' ? (apifyOn ? 'through Apify' : 'read directly') : 'through Apify';
          const checked = (form.sites || ['indeed']).includes(key) && covered;
          return `<label class="scout-site${!covered || (key !== 'indeed' && !direct && !apifyOn) ? ' is-off' : ''}"><input type="checkbox" name="sites" value="${key}" ${checked ? 'checked' : ''} ${covered ? '' : 'disabled'}><span><strong>${text}</strong><small>${note}</small></span></label>`;
        }).join('')}</div>${apifyOn ? '' : '<small class="scout-sites-hint">Sites other than Indeed and remote.id run through Apify — connect it in <button type="button" class="job-os-link" data-job-os-view="settings">Settings → Apify</button>.</small>'}</fieldset>
      </div>
      <label class="job-os-toggle"><input type="checkbox" name="remote_only" ${form.remote_only ? 'checked' : ''}><span class="job-os-toggle-track" aria-hidden="true"></span><span class="job-os-toggle-text"><strong>Remote only</strong><small>Search for remote roles and skip postings that are not remote</small></span></label>
      <p class="job-os-error" role="alert">${esc(state.searchError || '')}</p>
      <div class="job-os-actions"><button type="submit" class="job-os-btn primary">${editing ? 'Save search' : 'Create search'}</button><button type="button" class="job-os-btn" data-job-os-action="scout-form-close">Cancel</button></div></form></section>`;
  }
  // Good matches arrive together: they wait here until enough have collected
  // (or the evening cut-off), then show as new until marked seen.
  function matchInbox(state) {
    const box = state.matches;
    if (!box) return '';
    const released = box.released || [];
    const waiting = Number(box.waiting || 0);
    const rule = `Updates when ${box.release_count} good matches (${box.min_fit_score}%+) are waiting, or at ${String(box.release_cutoff_hour).padStart(2, '0')}:00.`;
    if (!released.length && !waiting) return '';
    const cards = released.map((m) => jobCard({...m, analysis: {status: 'done', fit_score: m.fit_score}, updated_at: m.released_at})).join('');
    return `<section class="job-os-card match-inbox${released.length ? ' has-new' : ''}">
      ${cardHead(released.length ? 'New good matches' : 'Good matches', 'applied', released.length ? '<button type="button" class="job-os-btn" data-job-os-action="matches-seen">Mark all seen</button>' : '', released.length || null)}
      <p class="job-os-card-note match-inbox-rule">${waiting ? `<strong>${waiting} waiting</strong> for the next update. ` : ''}${esc(rule)}</p>
      ${released.length ? `<div class="job-os-list scout-finds">${cards}</div>` : ''}</section>`;
  }
  function scoutView(state) {
    const searches = state.searches || [];
    const fc = state.firecrawl || {};
    const provider = state.searchProvider === 'brave' ? 'Brave Search API' : 'Firecrawl search';  // used only if Indeed refuses its results page
    const schedOn = !!(state.schedule && state.schedule.enabled);
    const viaApify = !!(state.apify && state.apify.active);
    const banner = !viaApify && fc.state && fc.state !== 'healthy'
      ? `<div class="scout-banner" role="status">${esc(fc.detail || 'Firecrawl is not ready.')} Scout can't run until it is. <button type="button" class="job-os-link" data-job-os-view="settings">Open Settings</button></div>` : '';
    const recent = (state.runs || []).filter((run) => run.counts && run.counts.saved && !ACTIVE_RUN.includes(run.status)).slice(0, 1)[0];
    const newIds = new Set(recent ? recent.new_job_ids : []);
    const finds = paged(newestFirst((state.jobs || []).filter((job) => newIds.has(job.id))), state.findsPage);
    const on = searches.filter((x) => x.enabled);
    const next = schedOn ? Math.min(...on.map((x) => Number(x.next_run_at) || Infinity)) : Infinity;
    const last = Math.max(0, ...searches.map((x) => Number(x.last_run_at) || 0));
    const tile = (iconName, label, value, note, attrs) => `<${attrs ? 'button type="button"' : 'div'} class="scout-tile"${attrs || ''}><span class="card-icon" aria-hidden="true">${icon(iconName, 16)}</span><span class="scout-tile-body"><small>${label}</small><strong>${value}</strong><span>${note}</span></span></${attrs ? 'button' : 'div'}>`;
    const overview = `<section class="scout-overview" aria-label="Scout at a glance">
      ${tile('cloud', 'Source', viaApify ? 'Apify' : 'This machine', viaApify ? esc(SITES.map(([, n]) => n).join(' · ')) : `Indeed, ${esc(provider)} as fallback`, ' data-job-os-action="settings-focus" data-section="apify"')}
      ${tile('calendar', 'Schedule', schedOn ? 'On' : 'Off', schedOn ? esc(state.schedule.summary || `Every ${state.schedule.hours}h`) : 'Turn on Run Scout automatically', ' data-job-os-action="settings-focus" data-section="scout"')}
      ${tile('clock', 'Next run', Number.isFinite(next) ? esc(until(next)) : '—', Number.isFinite(next) ? 'Latest of your searches' : schedOn ? 'No search is on' : 'Schedule off')}
      ${tile('radar', 'Searches', `${on.length} of ${searches.length}`, last ? `Last run ${esc(when(last))}` : 'Not run yet')}</section>`;
    return `${siteHealthBanner(state, 'scout')}${banner}${overview}${matchInbox(state)}
      ${searchFormCard(state.searchForm, state)}
      <div class="section-bar"><h2>Saved searches <span class="job-os-count">${searches.length}</span></h2><span class="scout-bar-spacer"></span><button type="button" class="job-os-btn primary" data-job-os-action="scout-new">${icon('import', 16)}New search</button></div>
      ${searches.length ? `<div class="scout-searches">${searches.map((x) => searchCard(x, state)).join('')}</div>`
        : (state.searchForm ? '' : '<section class="job-os-card job-os-empty"><strong>No saved searches yet</strong><p>Create one with the job titles you want, the country and, optionally, cities. Scout reads every posting it finds — title, company, pay and the full description — and adds it to your Pipeline.</p></section>')}
      ${finds.total ? `<section class="job-os-card">${cardHead('Latest finds', 'magic', '<button type="button" class="job-os-link" data-job-os-view="pipeline">View in Pipeline</button>', finds.total)}<div class="job-os-list scout-finds">${finds.rows.map(jobCard).join('')}</div>${pager('finds', finds)}</section>` : ''}`;
  }
  // ---- Job detail -------------------------------------------------------------
  function writingPanel(text) {
    return `<div class="writing-panel" role="status"><span class="writing-pen" aria-hidden="true"></span><div>${statusLine([text])}<div class="writing-lines"><i></i><i></i><i></i><i></i></div></div></div>`;
  }
  const DOC_STATUS = {pending: 'Queued', running: 'Writing', ready: 'Ready', needs_review: 'Needs review', failed: 'Failed'};
  function docStatus(status) { return `<span class="doc-status" data-status="${esc(status)}">${esc(DOC_STATUS[status] || status)}</span>`; }
  function tailoredList(state) {
    const items = state.tailored || [];
    if (!items.length) return `<section class="job-os-card">${cardHead('Tailored versions', 'magic')}<p class="job-os-card-note">Choose <strong>Tailor resume</strong> on any job with a description. Each tailored resume and cover letter appears here to review, edit and export.</p></section>`;
    return `<section class="job-os-card">${cardHead('Tailored versions', 'magic', '', items.length)}<div class="job-os-list">${items.map((d) => {
      const cov = d.notes && d.notes.coverage && d.notes.coverage.score;
      return `<button type="button" class="job-os-job-card studio-item" data-job-os-action="studio-open" data-job-id="${esc(d.job_id)}" data-key="doc-${esc(d.job_id)}"><span class="job-os-job-avatar" aria-hidden="true">${esc(String(d.job_company || d.job_title || '?').charAt(0).toUpperCase())}</span><span class="job-os-job-main"><strong>${esc(d.job_title)}</strong><span>${esc(d.job_company || '')}</span></span><span class="studio-item-tags">${cov != null ? `<span class="job-os-chip muted" title="Must-haves the resume mentions">${cov}% keywords</span>` : ''}${docStatus(d.status)}</span><small class="job-os-job-when">${esc(when(d.updated_at))}</small></button>`;
    }).join('')}</div></section>`;
  }
  function highlightNumbers(text, flags) {
    let out = esc(text);
    (flags || []).forEach((n) => { const e = esc(n).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); out = out.replace(new RegExp(`(^|[^\\w.])(${e})(?![\\w])`, 'g'), '$1<mark title="Not in your master resume">$2</mark>'); });
    return out;
  }
  function studioEditor(state) {
    const docs = state.studioDocs || {};
    const doc = docs[state.studioTab];
    const job = (state.tailored || []).find((d) => d.job_id === state.studioJobId) || {};
    const tabs = ['resume', 'cover_letter'].map((k) => `<button type="button" class="${state.studioTab === k ? 'active' : ''}" data-job-os-action="studio-tab" data-tab="${k}">${k === 'resume' ? 'Resume' : 'Cover letter'}${docs[k] ? ' ' + docStatus(docs[k].status) : ''}</button>`).join('');
    let body;
    if (!doc) body = '<p class="job-os-card-note">Nothing here yet.</p>';
    else if (['pending', 'running'].includes(doc.status)) body = writingPanel('Luna is writing…');
    else if (doc.status === 'failed') body = `<p class="job-os-error">${esc(doc.error || 'Tailoring failed.')}</p><button type="button" class="job-os-btn" data-job-os-action="studio-retry">Try again</button>`;
    else {
      const notes = doc.notes || {};
      const flags = notes.unverified || [];
      const cov = notes.coverage;
      const draft = state.studioDraft != null ? state.studioDraft : doc.content;
      const exportUrl = (fmt) => `/api/job-os/documents/${encodeURIComponent(doc.id)}/export?format=${fmt}`;
      body = `${flags.length ? `<div class="studio-warning" role="alert"><strong>Check before sending:</strong> ${flags.map((f) => `<code>${esc(f)}</code>`).join(' ')} ${flags.length === 1 ? 'is' : 'are'} not in your master resume. Fix or remove ${flags.length === 1 ? 'it' : 'them'}, then save.</div>` : ''}
        <div class="studio-grid"><div class="studio-edit"><textarea id="studio-text" spellcheck="true" aria-label="Edit document">${esc(draft)}</textarea>
          <div class="job-os-actions"><button type="button" class="job-os-btn primary" data-job-os-action="studio-save" ${state.studioDraft == null || state.studioDraft === doc.content ? 'disabled' : ''}>Save edits</button>
          <button type="button" class="job-os-btn" data-job-os-action="doc-preview" data-url="${exportUrl('html')}" data-title="${esc(`${state.studioTab === 'resume' ? 'Resume' : 'Cover letter'} — ${job.job_title || ''}`)}" ${state.studioDraft != null && state.studioDraft !== doc.content ? 'disabled title="Save your edits to preview them"' : ''}>${icon('eye', 16)}Preview</button>
          <a class="job-os-btn" href="${exportUrl('docx')}">${icon('download', 16)}DOCX</a><a class="job-os-btn" href="${exportUrl('pdf')}" target="_blank" rel="noopener">PDF</a><a class="job-os-btn" href="${exportUrl('md')}">Markdown</a></div></div>
        <aside class="studio-side">${state.studioTab === 'resume' ? fitCompare(notes) : ''}${state.studioTab === 'resume' && cov && cov.score != null ? `<div class="studio-box"><h4>Keyword coverage <span class="cov-score">${cov.score}%</span></h4><div class="job-os-chips">${(cov.found || []).map((k) => `<span class="job-os-chip" data-kind="remote">✓ ${esc(k)}</span>`).join('')}${(cov.missing || []).map((k) => `<span class="job-os-chip muted">${esc(k)}</span>`).join('')}</div></div>` : ''}
          ${state.studioTab === 'resume' ? reportBox(notes.report) : ''}
          ${(notes.changes || []).length ? `<div class="studio-box"><h4>What Luna changed</h4><ul class="analysis-list is-need">${notes.changes.map((c) => `<li><strong>${esc(c.what)}</strong>${c.why ? ` — ${esc(c.why)}` : ''}</li>`).join('')}</ul></div>` : ''}
          ${flags.length ? `<div class="studio-box"><h4>Preview</h4><div class="studio-preview">${highlightNumbers(doc.content, flags)}</div></div>` : ''}</aside></div>`;
    }
    const ready = job.job_status === 'resume_ready';
    return `<section class="job-os-card studio-editor" id="studio-editor"><div class="job-os-card-head"><div><h2>${esc(job.job_title || 'Tailored documents')}</h2><p class="job-os-card-note">${esc(job.job_company || '')}</p></div><div class="job-os-actions"><button type="button" class="job-os-btn" data-job-os-action="studio-close">${icon('prev', 16)}Back to list</button>${ready ? '<button type="button" class="job-os-btn primary" data-job-os-action="studio-ready">Ready to apply</button>' : ''}</div></div>
      <nav class="studio-tabs" aria-label="Document" data-mi-tabs>${tabs}</nav>${body}</section>`;
  }
  // ---- Resume Studio: how well the master resume matches one job ----------------------
  // The score as a ring: a soft track, the arc drawn to the score with rounded
  // ends in its band colour, the number in the middle.
  function matchRing(a) {
    const ring = (cls, attrs, fit, inner) => `<div class="match-ring${cls}"${attrs}><svg class="match-ring-svg" viewBox="0 0 120 120" aria-hidden="true"><circle class="match-ring-halo" cx="60" cy="60" r="57"/><circle class="match-ring-track" cx="60" cy="60" r="50"/>${fit == null ? '' : `<circle class="match-ring-arc" cx="60" cy="60" r="50" pathLength="100" style="--fit:${fit}"/>`}</svg><span class="match-ring-label">${inner}</span></div>`;
    if (!a) return ring(' is-empty', ' aria-label="Not scored yet"', null, '<strong>—</strong><small>Not scored</small>');
    if (['pending', 'running'].includes(a.status)) return ring(' is-busy', ' aria-label="Scoring"', 22, '<strong>…</strong><small>Scoring</small>');
    if (a.status === 'failed' || a.fit_score == null) return ring(' is-failed', ' aria-label="Scoring failed"', 100, '<strong>!</strong><small>Failed</small>');
    const [, key, text] = band(a.fit_score);
    const score = Number(a.fit_score);
    return ring('', ` data-band="${key}" role="img" aria-label="${esc(text)}: ${score} percent"`, Math.max(score, 1), `<strong>${score}<em>%</em></strong><small>${esc(text)}</small>`);
  }
  // The match check walks the jobs on the board in board order (New, then
  // Favorite, Ready to apply), newest first within a stage.
  const QUEUE_STAGES = [['new', ['scraped', 'analyzed']], ['favorite', ['shortlisted', 'tailoring']],
    ['ready', ['resume_ready', 'application_ready', 'awaiting_approval', 'applying']]];
  const STAGE_LABEL = {new: 'New', favorite: 'Favorite', ready: 'Ready to apply'};
  function matchQueue(jobs) {
    const fresh = newestFirst(jobs || []).filter((j) => j.has_description);
    return QUEUE_STAGES.flatMap(([stage, statuses]) => fresh.filter((j) => statuses.includes(j.status)).map((j) => Object.assign({stage}, j)));
  }
  function matchCheck(state) {
    if (!state.resume) return '';
    const queue = matchQueue(state.jobs);
    const automate = queue.length ? `<button type="button" class="job-os-btn" data-job-os-action="automate-all" title="Score every job here, then tailor a resume for each one at 50% or more">${icon('magic', 16)}Automate all</button>` : '';
    const head = cardHead('Match check', 'eye', automate);
    if (!queue.length) return `<section class="job-os-card match-card">${head}<p class="job-os-card-note card-empty-note">Jobs on your board with a description appear here one at a time. Save one from Scout or with <button type="button" class="job-os-link" data-job-os-action="job-form-new">Add job</button> to check your resume against it.</p></section>`;
    const at = Math.max(0, queue.findIndex((j) => j.id === state.studioMatchId));
    const item = queue[at];
    const job = state.studioMatch && state.studioMatch.id === item.id ? state.studioMatch : null;
    const a = job ? job.analysis : item.analysis || null;
    const list = (items, cls) => (items || []).length ? `<ul class="analysis-list ${cls}">${items.slice(0, 4).map((i) => `<li>${esc(i)}</li>`).join('')}</ul>` : '';
    const done = a && a.status === 'done';
    const busyNow = a && ['pending', 'running'].includes(a.status);
    const status = item.status;
    const canTailor = ['scraped', 'analyzed', 'shortlisted', 'resume_ready', 'application_ready'].includes(status);
    const retailor = ['resume_ready', 'application_ready'].includes(status);
    const hasDocs = ['tailoring', 'resume_ready', 'application_ready'].includes(status) || (state.tailored || []).some((d) => d.job_id === item.id);
    const nextId = queue[at + 1] ? queue[at + 1].id : '';
    const actions = [
      canTailor && !retailor ? `<button type="button" class="job-os-btn primary" data-job-os-action="match-tailor" data-job-id="${esc(item.id)}" data-next-id="${esc(nextId)}">${icon('magic', 16)}${nextId ? 'Tailor & next' : 'Tailor resume'}</button>` : '',
      busyNow ? '' : `<button type="button" class="job-os-btn${done || canTailor ? '' : ' primary'}" data-job-os-action="match-score" data-job-id="${esc(item.id)}">${done ? 'Score again' : 'Score my resume'}</button>`,
      retailor ? `<button type="button" class="job-os-btn" data-job-os-action="card-tailor" data-job-id="${esc(item.id)}">Tailor again</button>` : '',
      hasDocs ? `<button type="button" class="job-os-btn${retailor ? ' primary' : ''}" data-job-os-action="studio-open" data-job-id="${esc(item.id)}">Open tailored resume</button>` : '',
      `<button type="button" class="job-os-btn" data-job-id="${esc(item.id)}">Open job</button>`,
    ].join('');
    const nav = (to, label, iconName) => `<button type="button" class="job-os-icon-btn match-step" data-job-os-action="match-go" data-job-id="${esc(to ? to.id : '')}" aria-label="${label}" title="${label} (${iconName === 'prev' ? '←' : '→'})" ${to ? '' : 'disabled'}>${icon(iconName, 18)}</button>`;
    const meta = [item.company, place(item), SOURCE_LABEL[sourceOf(item)]].filter(Boolean).map(esc).join(' · ');
    return `<section class="job-os-card match-card">${head}
      <div class="match-nav">${nav(queue[at - 1], 'Previous job', 'prev')}
        <div class="match-job" aria-live="polite"><span class="match-stage" data-stage="${esc(item.stage)}">${esc(STAGE_LABEL[item.stage])}</span><strong>${esc(item.title)}</strong><span>${meta}</span></div>
        <span class="match-count">${at + 1} <small>of ${queue.length}</small></span>${nav(queue[at + 1], 'Next job', 'next')}</div>
      <div class="match-progress" aria-hidden="true"><i style="width:${Math.round(100 * (at + 1) / queue.length)}%"></i></div>
      <div class="match-body" data-job="${esc(item.id)}">${matchRing(a)}<div class="match-detail">
        ${done && job && job.analysis.summary ? `<p>${esc(job.analysis.summary)}</p>` : `<p class="job-os-card-note">${busyNow ? statusLine(['Reading the posting…', 'Comparing it with your resume…', 'Scoring the match…']) : done ? '' : 'Not scored yet. Scoring takes a few seconds and uses one model call.'}</p>`}
        ${done && job ? `<div class="analysis-cols">${job.analysis.strengths && job.analysis.strengths.length ? `<div><h4>Matches</h4>${list(job.analysis.strengths, 'is-good')}</div>` : ''}${job.analysis.gaps && job.analysis.gaps.length ? `<div><h4>Missing</h4>${list(job.analysis.gaps, 'is-gap')}</div>` : ''}</div>` : ''}
        <p class="match-legend" aria-hidden="true"><span data-band="good">75–100 Good match</span><span data-band="fair">50–74 Needs improvement</span><span data-band="poor">0–49 Terrible match</span></p>
      </div></div>
      <div class="job-os-actions match-actions">${actions}</div></section>`;
  }
  // The tailoring method's working: how the resume's bullets met the job,
  // what was reworded and why it is still true, and the gaps it left alone.
  function reportBox(report) {
    if (!report) return '';
    const m = report.mapping || {};
    const total = ['direct', 'transferable', 'adjacent'].reduce((n, k) => n + (m[k] || 0), 0);
    const bar = total ? `<div class="map-bar" role="img" aria-label="${m.direct || 0} direct, ${m.transferable || 0} transferable, ${m.adjacent || 0} adjacent bullets">${['direct', 'transferable', 'adjacent'].map((k) => m[k] ? `<i data-kind="${k}" style="flex:${m[k]}"></i>` : '').join('')}</div>
      <p class="map-legend">${['direct', 'transferable', 'adjacent'].map((k) => `<span data-kind="${k}">${m[k] || 0} ${k}</span>`).join('')}${m.gaps ? `<span data-kind="gap">${m.gaps} gap${m.gaps === 1 ? '' : 's'}</span>` : ''}</p>` : '';
    const terms = (report.terms || []).map((t) => `<li><span>${esc(t.from)}</span>${icon('next', 12)}<strong>${esc(t.to)}</strong></li>`).join('');
    const reframes = (report.reframings || []).map((r) => `<li><del>${esc(r.original)}</del><ins>${esc(r.reframed)}</ins>${r.why ? `<small>${esc(r.why)}</small>` : ''}</li>`).join('');
    const gaps = (report.gaps || []).map((g) => `<li><strong>${esc(g.need)}</strong>${g.advice ? ` — ${esc(g.advice)}` : ''}</li>`).join('');
    const questions = (report.questions || []).map((q) => `<li>${esc(q)}</li>`).join('');
    return `<div class="studio-box report-box"><h4>How Luna tailored it</h4>${bar}
      ${(report.core || []).length ? `<h5>What the role needs</h5><div class="job-os-chips">${report.core.map((c) => `<span class="job-os-chip">${esc(c)}</span>`).join('')}${(report.valued || []).map((c) => `<span class="job-os-chip muted">${esc(c)}</span>`).join('')}</div>` : ''}
      ${terms ? `<h5>In the posting's words</h5><ul class="report-terms">${terms}</ul>` : ''}
      ${reframes ? `<details class="report-more"><summary>Reworded (${report.reframings.length})</summary><ul class="report-reframes">${reframes}</ul></details>` : ''}
      ${gaps ? `<h5>Left out — not in your resume</h5><ul class="analysis-list is-gap">${gaps}</ul>` : ''}
      ${questions ? `<h5>Worth asking yourself</h5><ul class="analysis-list is-need">${questions}</ul><p class="job-os-card-note">If any is true, add it to your master resume and tailor again.</p>` : ''}</div>`;
  }
  // Master vs tailored: both scored by Luna with the same prompt, so the gain is real.
  function fitCompare(notes) {
    const fit = notes.tailored_fit || null;
    const master = notes.master_fit;
    const ring = (score) => (score == null ? emptyRing('', '—') : fitRing({status: 'done', fit_score: score}));
    let tailored;
    if (!fit) tailored = emptyRing('', '—');
    else if (fit.status === 'running') tailored = emptyRing(' is-busy', '…');
    else if (fit.status === 'failed') tailored = emptyRing(' is-failed', '!');
    else tailored = ring(fit.fit_score);
    const gain = fit && fit.status === 'done' && master != null ? fit.fit_score - master : null;
    return `<div class="studio-box fit-compare"><h4>Match with this job</h4>
      <div class="fit-compare-row"><div>${ring(master)}<small>Master</small></div><span class="fit-compare-arrow" aria-hidden="true">→</span><div>${tailored}<small>Tailored</small></div>
        ${gain != null ? `<strong class="fit-gain" data-up="${gain >= 0}">${gain >= 0 ? '+' : ''}${gain}</strong>` : ''}</div>
      ${fit && fit.stale ? '<p class="job-os-card-note">Scored before your last edits.</p>' : ''}
      ${fit && fit.status === 'failed' ? `<p class="job-os-card-note">${esc(fit.error || 'Scoring failed.')}</p>` : ''}
      ${!fit || fit.status !== 'running' ? `<button type="button" class="job-os-btn small" data-job-os-action="studio-rescore">${fit && fit.status === 'done' ? 'Score again' : 'Score it'}</button>` : '<p class="job-os-card-note">Scoring…</p>'}</div>`;
  }
  function tailoredView(state) {
    return state.studioJobId ? studioEditor(state) : tailoredList(state);
  }
  function detailActions(job) {
    const out = [];
    const a = job.analysis;
    const st = job.status;
    const fresh = ['discovered', 'scraped', 'analyzed', 'shortlisted'].includes(st);
    if (!job.description && sourceOf(job) === 'indeed') out.push('<button type="button" class="job-os-btn primary" data-job-os-action="job-details">Fetch details</button>');
    if (['scraped', 'analyzed'].includes(st)) out.push(`<button type="button" class="job-os-btn${job.description ? '' : ' primary'}" data-job-os-action="job-status" data-status="shortlisted">Add to Favorite</button>`);
    if (['scraped', 'analyzed', 'shortlisted'].includes(st) && job.description) out.push('<button type="button" class="job-os-btn primary" data-job-os-action="job-tailor">Tailor resume</button>');
    if (['resume_ready', 'application_ready'].includes(st)) out.push(`<button type="button" class="job-os-btn primary" data-job-os-action="studio-open" data-job-id="${esc(job.id)}">Open in Resume Studio</button>`);
    if (st === 'resume_ready') out.push('<button type="button" class="job-os-btn" data-job-os-action="job-ready">Ready to apply</button>');
    if (fresh || ['resume_ready', 'application_ready'].includes(st)) out.push(`<button type="button" class="job-os-btn" data-job-os-action="board-apply" data-job-id="${esc(job.id)}" data-url="${esc(job.canonical_url)}">Mark applied</button>`);
    if (job.description && !analysing(job)) out.push(`<button type="button" class="job-os-btn" data-job-os-action="job-analyze">${a && a.status === 'done' ? 'Score again' : 'Score resume'}</button>`);
    if (fresh) out.push('<button type="button" class="job-os-btn" data-job-os-action="job-status" data-status="skipped">Skip</button>');
    const prep = job.interview;
    if (['screening', 'interviewing', 'offer'].includes(st) && !(prep && ['pending', 'running'].includes(prep.status))) {
      out.unshift(`<button type="button" class="job-os-btn${prep && prep.status === 'done' ? '' : ' primary'}" data-job-os-action="job-interview">${prep && prep.status === 'done' ? 'Refresh interview prep' : 'Prepare for interview'}</button>`);
    }
    return out.join('');
  }
  function analysisPanel(job) {
    const a = job.analysis;
    if (!a) return '';
    if (analysing(job)) return `<div class="job-os-analysis is-busy">${emptyRing(' large is-busy', '…')}<div>${statusLine(['Luna is reading the posting…', 'Comparing it with your resume…', 'Scoring the match…'])}<div class="analysis-shimmer"><i></i><i></i><i></i></div></div></div>`;
    if (a.status === 'failed') return `<div class="job-os-analysis is-failed">${emptyRing(' large is-failed', '!')}<div><strong>Analysis failed</strong><p>${esc(a.error || '')}</p></div></div>`;
    const list = (items, cls) => (items || []).length ? `<ul class="analysis-list ${cls}">${items.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>` : '';
    return `<div class="job-os-analysis">${fitRing(a, 'large')}<div class="analysis-body"><div class="analysis-head"><strong class="analysis-verdict" data-band="${band(a.fit_score)[1]}">${esc(band(a.fit_score)[2])} · ${Number(a.fit_score)}%</strong>${a.seniority ? `<span class="job-os-chip muted">${esc(a.seniority)}</span>` : ''}</div>
      ${a.summary ? `<p>${esc(a.summary)}</p>` : ''}
      <div class="analysis-cols">${a.strengths && a.strengths.length ? `<div><h4>Strengths</h4>${list(a.strengths, 'is-good')}</div>` : ''}${a.gaps && a.gaps.length ? `<div><h4>Gaps</h4>${list(a.gaps, 'is-gap')}</div>` : ''}${a.must_haves && a.must_haves.length ? `<div><h4>Must-haves</h4>${list(a.must_haves, 'is-need')}</div>` : ''}</div>
      ${a.salary_note ? `<p class="job-os-card-note">${esc(a.salary_note)}</p>` : ''}</div></div>`;
  }
  // ---- Resume Studio ---------------------------------------------------------
  function resumeView(state) {
    const r = state.resume;
    const upload = `<div class="resume-drop" id="resume-drop" tabindex="0" role="button" aria-label="Upload resume"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/></svg><strong>Drop your resume here</strong><span>or click to choose · PDF, DOCX, Markdown or text · up to 5 MB</span><input type="file" id="resume-file" accept=".pdf,.docx,.md,.markdown,.txt" hidden></div>
      <details class="resume-paste"><summary>Paste text instead</summary><textarea id="resume-text" rows="8" placeholder="Paste your resume text"></textarea><button type="button" class="job-os-btn" data-job-os-action="resume-paste">Save pasted resume</button></details>
      <p class="job-os-error" role="alert">${esc(state.resumeError || '')}</p>`;
    if (!r || state.resumeReplacing) {
      return `<section class="job-os-card"><div class="job-os-card-head"><h2>${r ? 'Replace your master resume' : 'Your master resume'}</h2>${r ? '<button type="button" class="job-os-link" data-job-os-action="resume-cancel">Cancel</button>' : ''}</div><p class="job-os-card-note">Everything Hermes tailors comes from this file. It only rephrases, reorders and selects from it; it never adds experience you do not have.</p>${upload}</section>`;
    }
    const design = r.style || {};
    const swatches = [design.heading && design.heading.color, design.name && design.name.color, design.body && design.body.color]
      .filter((c, i, all) => c && all.indexOf(c) === i).map((c) => `<i style="background:${esc(c)}"></i>`).join('');
    const designNote = design.source === 'file'
      ? `${esc(design.font || '')} · ${design.page === 'letter' ? 'Letter' : 'A4'} · ${design.align_header === 'center' ? 'centred header' : 'left-aligned header'}${design.heading && design.heading.rule ? ' · ruled headings' : ''}`
      : 'Neutral design (upload a PDF or DOCX to keep your own)';
    const kind = state.resumeOriginal === 'pdf' ? 'pdf' : 'html';
    // The first page, once drawn, is kept as an image so redraws don't flicker.
    const thumb = state.resumeThumb && state.resumeThumb.revision === r.revision && /^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(state.resumeThumb.url) ? state.resumeThumb.url : '';
    return `<section class="job-os-card resume-master">${cardHead('Master resume', 'resume-studio', `${state.resumeOriginal ? `<a class="job-os-btn" href="/api/job-os/resume/original" ${state.resumeOriginal === 'pdf' ? 'target="_blank" rel="noopener"' : 'download'}>${icon('download', 16)}Original</a>` : ''}<button type="button" class="job-os-btn" data-job-os-action="resume-replace">Replace</button>`)}
      <div class="resume-master-body">
        <button type="button" class="resume-thumb" data-job-os-action="resume-preview" data-kind="${kind}" aria-label="Open a full preview of your master resume" title="Preview">
          <span class="resume-thumb-page${thumb ? ' is-drawn' : ''}" id="resume-thumb" data-kind="${kind}" data-keep="${kind}-${Number(r.revision || 0)}">${kind === 'html' ? '<iframe src="/api/job-os/resume/preview" title="Resume thumbnail" tabindex="-1" aria-hidden="true" loading="lazy"></iframe>' : thumb ? `<img src="${thumb}" alt="">` : '<span class="resume-thumb-loading" aria-hidden="true"></span>'}</span>
          <span class="resume-thumb-hint">${icon('expand', 14)}Preview</span></button>
        <div class="resume-master-info">
          <strong class="resume-file">${esc(r.filename)}</strong>
          <div class="job-os-chips"><span class="job-os-chip muted">${Number(r.words || 0).toLocaleString()} words</span><span class="job-os-chip muted">Updated ${esc(when(r.uploaded_at))}</span><span class="job-os-chip muted">Version ${Number(r.revision || 1)}</span></div>
          <div class="resume-design"><span class="resume-swatches" aria-hidden="true">${swatches}</span><span><strong>Design kept for tailoring</strong><small>${designNote}</small></span></div>
          <p class="job-os-card-note">Every tailored resume comes from this file and is laid out like it: same sections, same header, same look. Luna only rephrases, reorders and selects; it never adds experience you do not have.</p>
          <details class="job-os-desc-wrap"><summary>Show text</summary><div class="job-os-description">${esc(r.text)}</div></details>
        </div>
      </div></section>`;
  }
  // Full-size preview of the master (or a tailored) resume: click anywhere to close.
  function resumePreview(state) {
    const p = state.resumePreview;
    if (!p) return '';
    return `<div class="resume-preview" data-job-os-action="resume-preview-close" role="dialog" aria-label="Resume preview" tabindex="-1">
      <div class="resume-preview-bar"><span>${esc(p.title || 'Resume')}</span><small>Click anywhere or press Esc to close</small></div>
      <div class="resume-preview-pages" id="resume-preview-pages" data-kind="${esc(p.kind)}" data-keep="${esc(p.kind)}:${esc(p.url)}">${p.kind === 'html' ? `<iframe src="${esc(p.url)}" title="${esc(p.title || 'Resume')}"></iframe>` : '<span class="resume-thumb-loading" aria-hidden="true"></span>'}</div></div>`;
  }
  function interviewPanel(job) {
    const p = job.interview;
    if (!p) return '';
    if (['pending', 'running'].includes(p.status)) return writingPanel('Luna is preparing interview questions, stories and research for this job…');
    if (p.status === 'failed') return `<div class="job-os-analysis is-failed"><div><strong>Interview prep failed</strong><p>${esc(p.error || '')}</p></div></div>`;
    const list = (items) => (items || []).map((i) => `<li>${esc(i)}</li>`).join('');
    const questions = (p.questions || []).map((q) => `<details class="prep-q"${q.supported ? '' : ' data-gap="true"'}><summary>${esc(q.question)}${q.supported ? '' : '<span class="job-os-chip muted">Prepare</span>'}</summary>${q.why ? `<p class="prep-why">${esc(q.why)}</p>` : ''}<p>${esc(q.outline)}</p></details>`).join('');
    const stories = (p.stories || []).map((s) => `<div class="prep-story"><strong>${esc(s.title)}</strong><dl><dt>Situation</dt><dd>${esc(s.situation)}</dd><dt>Action</dt><dd>${esc(s.action)}</dd><dt>Result</dt><dd>${esc(s.result)}</dd></dl>${s.use_for ? `<small>Use for: ${esc(s.use_for)}</small>` : ''}</div>`).join('');
    const block = (title, items) => (items || []).length ? `<div><h4>${title}</h4><ul class="analysis-list">${list(items)}</ul></div>` : '';
    return `<section class="job-os-prep"><div class="job-os-card-head"><h3>Interview prep</h3><a class="job-os-link" href="/api/job-os/jobs/${encodeURIComponent(job.id)}/interview-prep.md" download>Download</a></div>
      <h4>Likely questions</h4><div class="prep-questions">${questions}</div>
      ${stories ? `<h4>Stories to rehearse</h4><div class="prep-stories">${stories}</div>` : ''}
      <div class="analysis-cols">${block('Ask them', p.ask_them)}${block('Research', p.research)}${block('Watch-outs', p.watch_outs)}</div></section>`;
  }
  function shell(state) {
    useSites(state.sites || (state.settingsStatus && state.settingsStatus.apify && state.settingsStatus.apify.sites));
    const view = state.activeView;
    const dashboard = dashboardOf(state);
    const byStatus = dashboard.by_status || {};
    const jobs = newestFirst(state.jobs || []);
    const draft = state.importDraft || {};
    let body;
    if (view === 'dashboard') {
      const recent = paged(jobs, state.recentPage);
      body = `${header('Dashboard', 'Your job search at a glance.', state)}${siteHealthBanner(state, 'dashboard')}
        <section class="job-os-metrics" aria-label="Job dashboard">${metric('total', dashboard.total_jobs, 'Total jobs', 'data-job-os-filter=""')}${metric('active', dashboard.active_work, 'Active work', 'data-job-os-filter="active"')}${metric('attention', dashboard.needs_attention, 'Needs attention', 'data-job-os-view="pipeline"')}${metric('applied', appliedCount(byStatus), 'Applied', 'data-job-os-filter="applied"')}</section>
        <div class="job-os-pair">${automationsCard(state.automations) || '<section class="job-os-card automations-card is-loading" aria-busy="true"></section>'}${funnelCard(dashboard.funnel, dashboard.activity, state.activityMonth || 0)}</div>
        <div class="job-os-columns">
          <section class="job-os-card job-os-recent">${cardHead('Recent jobs', 'briefcase', '<button type="button" class="job-os-link" data-job-os-view="pipeline">View pipeline</button>', jobs.length || null)}${jobList(recent.rows, 'No jobs saved yet', 'Add a job or run Scout to start tracking roles through your pipeline.')}${pager('recent', recent)}</section>
          <section class="job-os-card job-os-import">${cardHead('Track a job', 'import')}<p class="job-os-card-note">Manually save jobs, tailor your resume to it, then follow through on your pipeline.</p><button class="job-os-btn primary" type="button" data-job-os-action="job-form-new">${icon('import', 16)}Add job</button></section>
        </div>${jobForm(state)}`;
    } else if (view === 'pipeline') {
      const filter = state.statusFilter;
      const group = STATUS_GROUPS[filter];
      const scoped = jobs.filter((j) => (!group || group.statuses.includes(j.status)) && shownOn(state)(j));
      const counts = state.board && state.board.sources ? state.board.sources
        : Object.fromEntries([['all', jobs.length], ...Object.keys(SOURCE_LABEL).map((k) => [k, jobs.filter((j) => sourceOf(j) === k).length])]);
      const listMode = state.pipelineMode === 'list' || filter;
      const empty = group ? `<div class="job-os-empty"><strong>Nothing in ${esc(group.label.toLowerCase())} yet</strong><p>${esc(group.empty)}</p></div>`
        : state.pipelineQuery ? noMatches(state) : emptyPipeline(state);
      const list = `<section class="job-os-card job-os-fill"><div class="job-os-card-head"><h2>${filter ? `<span class="job-os-filter-label">${esc(statusLabel(filter))}</span>` : 'All jobs'} <span class="job-os-count">${scoped.length}</span></h2>${filter ? '<button type="button" class="job-os-link" data-job-os-filter="">Show the board</button>' : ''}</div>${scoped.length ? jobList(sortJobs(scoped, state.sortBy), '', '') : empty}</section>`;
      body = `${header('Pipeline', 'Every job from new find to offer — Scout’s finds from the job sites, and the ones you track yourself.', state)}
        ${pipelineBar(state, jobs, counts)}
        ${listMode ? list : pipelineBoard(state)}
        ${jobDrawer(state)}${jobForm(state)}`;
    } else if (view === 'logistics') {
      const legend = [['strong', 'Strong fit'], ['good', 'Good fit'], ['stretch', 'Stretch'], ['poor', 'Poor fit'], ['none', 'Not scored']]
        .map(([key, text]) => `<span><i data-verdict="${key}"></i>${text}</span>`).join('');
      body = `${header('Logistics centre', 'Every job is a parcel moving through the warehouse. Click one to open it.', state)}
        <section class="logistics-wrap"><div id="job-os-logistics-slot" class="logistics-stage" data-slide-safe data-keep="logistics"></div><div class="logistics-legend" aria-label="Parcel colours">${legend}<span class="logistics-legend-hint">Scroll to zoom</span></div></section>`;
    } else if (view === 'scout') {
      body = `${header('Scout', 'Saved searches find new postings on Indeed and LinkedIn and save each one into your Pipeline.', state)}${scoutView(state)}${jobForm(state)}`;
    } else if (view === 'settings') {
      body = `${header('Settings', 'Connections, AI, schedules and notifications for this profile.', state)}${settingsView(state)}`;
    } else {
      body = `${header('Resume Studio', 'Your master resume, how well it matches each job, and the versions tailored from it.', state)}${resumeView(state)}${state.studioJobId ? '' : matchCheck(state)}${tailoredView(state)}${jobForm(state)}${resumePreview(state)}`;
    }
    return `<div class="job-os-shell" data-view="${esc(view)}">${mobileNav(view, state)}<main class="job-os-content">${body}</main></div>`;
  }
  function sidebar(state) {
    const view = state.activeView;
    const dashboard = dashboardOf(state);
    const byStatus = dashboard.by_status || {};
    const fresh = state.matches ? (state.matches.released || []).length : 0;
    const counts = {pipeline: dashboard.total_jobs, scout: fresh};
    const nav = sectionsOf(state).map((key) => {
      const active = view === key && !(key === 'pipeline' && (state.statusFilter || state.focusColumn));
      const alert = key === 'scout' && siteProblems(state).some((site) => site.in_use !== false);
      if (alert) return `<button type="button" class="side-menu-item${active ? ' active' : ''}" data-job-os-view="${key}"${active ? ' aria-current="page"' : ''}>${icon(key, 18)}<span class="side-menu-label">${labels[key]}</span><span class="job-os-side-alert" title="A job site needs attention" aria-label="A job site needs attention">!</span></button>`;
      const count = counts[key] ? `<span class="job-os-side-count${key === 'scout' ? ' is-new' : ''}"${key === 'scout' ? ` title="${counts[key]} new good match${counts[key] === 1 ? '' : 'es'}"` : ''}>${counts[key]}</span>` : '';
      return `<button type="button" class="side-menu-item${active ? ' active' : ''}" data-job-os-view="${key}"${active ? ' aria-current="page"' : ''}>${icon(key, 18)}<span class="side-menu-label">${labels[key]}</span>${count}</button>`;
    }).join('');
    // Every board column, in board order; a click opens the board at that column.
    const stages = STAGES.map(([key, label, statuses]) => {
      const n = statuses.reduce((sum, status) => sum + (byStatus[status] || 0), 0);
      const active = view === 'pipeline' && state.focusColumn === key;
      return `<button type="button" class="side-menu-item job-os-stage${active ? ' active' : ''}${n ? '' : ' is-empty'}" data-job-os-stage="${key}" data-col="${key}" title="Open ${esc(label)} on the board"><span class="job-os-stage-dot" aria-hidden="true"></span><span class="side-menu-label">${esc(label)}</span><span class="job-os-side-count">${n}</span></button>`;
    }).join('');
    return `${apifyWidget(state.apifyUsage)}<nav class="side-menu job-os-side-nav" aria-label="Job OS sections" data-mi-tabs="y">${nav}</nav><div class="job-os-side-section"><div class="job-os-side-heading">Pipeline stages</div><div class="side-menu job-os-side-stages">${stages}</div></div>`;
  }
  window.JobOSRender = {shell, sidebar, runBody, matchQueue, STATUS_GROUPS, settingsPageOf, LOADING};
}());
