import { createRoot } from 'react-dom/client';
import './styles/base.css';

const root = createRoot(document.getElementById('root')!);
if (new URLSearchParams(location.search).get('quick') === '1') {
  void import('./components/QuickPanel').then(({ QuickPanel }) => root.render(<QuickPanel />));
} else {
  void import('./App').then(({ App }) => root.render(<App />));
}
