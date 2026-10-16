// Image generation placeholders/reveals. Separate because it pulls in three.js
// (resolved to the app's vendored copy, static/vendor/three).
import { ImageGeneration } from 'img-fx';
import { register } from './mount.jsx';

register({ ImageGeneration });
export { ImageGeneration };
