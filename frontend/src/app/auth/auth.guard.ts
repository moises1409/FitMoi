import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map, of } from 'rxjs';
import { AuthService } from '../services/auth.service';

/**
 * Protege las rutas de la app. Consulta el estado del candado la primera vez
 * (después usa la caché); si hace falta entrar y no se ha entrado, manda al
 * login. Con el candado desactivado (dev local) deja pasar siempre.
 */
export const authGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  const decide = () =>
    auth.needsLogin()
      ? router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } })
      : true;

  if (auth.statusChecked) return of(decide());
  return auth.ensureStatus().pipe(map(decide));
};
