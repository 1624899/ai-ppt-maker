import clsx from 'clsx';
import sharedStyles from '../components/styles/shared.module.css';
import taskStyles from '../components/styles/tasks.module.css';
import workspaceStyles from '../components/styles/workspace.module.css';
import formStyles from '../components/styles/forms.module.css';
import studioStyles from '../components/styles/studio.module.css';
import overlayStyles from '../components/styles/overlays.module.css';
import responsiveStyles from '../components/styles/responsive.module.css';

const styleModules = [
  sharedStyles,
  taskStyles,
  workspaceStyles,
  formStyles,
  studioStyles,
  overlayStyles,
  responsiveStyles,
];

const mapClassToken = (token) => {
  const scopedTokens = styleModules.map((styles) => styles[token]).filter(Boolean);
  return scopedTokens.length > 0 ? scopedTokens.join(' ') : token;
};

const mapClassString = (value) => String(value || '')
  .split(/\s+/)
  .filter(Boolean)
  .map(mapClassToken)
  .join(' ');

const mapClassValue = (value) => {
  if (typeof value === 'string') return mapClassString(value);
  if (Array.isArray(value)) return value.map(mapClassValue);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, enabled]) => [mapClassString(key), enabled]),
    );
  }
  return value;
};

export const uiClassName = (...values) => clsx(...values.map(mapClassValue));
