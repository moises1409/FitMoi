import {
  AfterViewChecked,
  Component,
  ElementRef,
  OnInit,
  ViewChild,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { CoachService } from '../services/coach.service';
import { CoachMessage } from '../models/coach.model';

/** Preguntas de arranque: dan pistas de para qué sirve el entrenador. */
const SUGGESTIONS = [
  '¿Cómo llevo la semana?',
  '¿Voy bien de proteína?',
  '¿Qué entreno me conviene mañana?',
  '¿Por qué no baja el peso?',
];

@Component({
  selector: 'app-coach-chat',
  standalone: true,
  imports: [FormsModule, RouterLink, MatIconModule, MatSnackBarModule],
  templateUrl: './coach-chat.component.html',
  styleUrl: './coach-chat.component.scss',
})
export class CoachChatComponent implements OnInit, AfterViewChecked {
  private coach = inject(CoachService);
  private snack = inject(MatSnackBar);

  @ViewChild('scroller') scroller?: ElementRef<HTMLElement>;

  readonly suggestions = SUGGESTIONS;
  messages = signal<CoachMessage[]>([]);
  draft = '';
  sending = signal(false);
  loading = signal(true);

  /** Solo se muestran las sugerencias cuando la charla aún está por empezar. */
  readonly showSuggestions = computed(
    () => this.messages().length <= 1 && !this.sending(),
  );

  private shouldScroll = false;

  ngOnInit(): void {
    this.coach.load().subscribe({
      next: (conv) => {
        this.messages.set(conv.messages ?? []);
        this.loading.set(false);
        this.shouldScroll = true;
      },
      error: () => {
        this.loading.set(false);
        this.snack.open('No se pudo cargar la conversación', 'OK');
      },
    });
  }

  ngAfterViewChecked(): void {
    if (!this.shouldScroll) return;
    this.shouldScroll = false;
    const el = this.scroller?.nativeElement;
    if (el) el.scrollTop = el.scrollHeight;
  }

  ask(text: string): void {
    this.draft = text;
    this.send();
  }

  send(): void {
    const message = this.draft.trim();
    if (!message || this.sending()) return;

    this.draft = '';
    this.sending.set(true);
    this.messages.update((list) => [...list, { role: 'user', content: message }]);
    this.shouldScroll = true;

    this.coach.send(message).subscribe({
      next: (res) => {
        this.sending.set(false);
        this.messages.update((list) => [
          ...list,
          { role: 'assistant', content: res.reply },
        ]);
        this.shouldScroll = true;
      },
      error: (err) => {
        this.sending.set(false);
        // Se devuelve lo escrito al cuadro de texto para no perderlo.
        this.messages.update((list) => list.slice(0, -1));
        this.draft = message;
        this.snack.open(
          err?.error?.error ?? 'No se pudo enviar. Inténtalo de nuevo.',
          'OK',
          { duration: 6000 },
        );
      },
    });
  }

  onKeydown(event: KeyboardEvent): void {
    // Enter envía; Shift+Enter hace salto de línea.
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.send();
    }
  }

  reset(): void {
    this.coach.reset().subscribe({
      next: (conv) => {
        this.messages.set(conv.messages ?? []);
        this.shouldScroll = true;
        this.snack.open('Charla reiniciada.', 'OK', { duration: 3000 });
      },
      error: () => this.snack.open('No se pudo reiniciar', 'OK'),
    });
  }
}
