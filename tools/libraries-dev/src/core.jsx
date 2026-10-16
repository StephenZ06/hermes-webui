// The light libraries, loaded together (no WebGL scene libraries here).
import { BorderBeam } from 'border-beam';
import { ThinkingOrb } from 'thinking-orbs';
import { BotAvatar } from 'bot-avatars';
import { Liquid } from 'liquid-gooey';
import { VoiceBeam } from 'voice-glow';
import { MetalFx, MetalText, MetalBadge, isMetalFxSupported } from 'metal-fx';
import { register, mount, wrap, React } from './mount.jsx';

register({ BorderBeam, ThinkingOrb, BotAvatar, Liquid, LiquidItem: Liquid.Item, VoiceBeam, MetalFx, MetalText, MetalBadge });

export const LibrariesDev = { mount, wrap, register, React, isMetalFxSupported, version: __LIBDEV_VERSION__ };
export { mount, wrap, register, React, isMetalFxSupported };
