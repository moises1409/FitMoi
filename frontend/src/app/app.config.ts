import { ApplicationConfig, LOCALE_ID } from '@angular/core';
import { registerLocaleData } from '@angular/common';
import localeEs from '@angular/common/locales/es';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideAnimations } from '@angular/platform-browser/animations';
import { MAT_SNACK_BAR_DEFAULT_OPTIONS } from '@angular/material/snack-bar';
import { routes } from './app.routes';
import { authInterceptor } from './auth/auth.interceptor';

// Sin esto, `| date:'EEEE'` lanza NG0701 (faltan datos del locale) y la
// excepción aborta el renderizado del resto de la plantilla.
registerLocaleData(localeEs, 'es');

export const appConfig: ApplicationConfig = {
  providers: [
    { provide: LOCALE_ID, useValue: 'es' },
    provideRouter(routes),
    provideHttpClient(withInterceptors([authInterceptor])),
    provideAnimations(),
    { provide: MAT_SNACK_BAR_DEFAULT_OPTIONS, useValue: { duration: 3000, horizontalPosition: 'center', verticalPosition: 'bottom' } },
  ]
};
