import { inject } from '@angular/core';
import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { AuthService } from '../services/auth.service';

/**
 * Ante un 401 (cookie caducada o token cambiado) marca la sesión como cerrada
 * y lleva al login, guardando a dónde iba el usuario para volver luego. El
 * propio login se deja pasar para no entrar en un bucle de redirecciones.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  return next(req).pipe(
    catchError((err: HttpErrorResponse) => {
      const isLoginCall = req.url.includes('/auth/login');
      if (err.status === 401 && !isLoginCall) {
        auth.markLoggedOut();
        if (!router.url.startsWith('/login')) {
          router.navigate(['/login'], { queryParams: { returnUrl: router.url } });
        }
      }
      return throwError(() => err);
    }),
  );
};
