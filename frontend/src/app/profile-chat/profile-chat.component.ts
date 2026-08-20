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
import { Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ProfileService } from '../services/profile.service';
import { ChatMessage, FIELD_LABELS } from '../models/profile.model';

/** Un turno ya pintado, con lo que el entrenador anotó en él. */
interface Turn extends ChatMessage {
  noted?: string[];
}

@Component({
  selector: 'app-profile-chat',
  standalone: true,
  imports: [FormsModule, RouterLink, MatIconModule, MatSnackBarModule],
  templateUrl: './profile-chat.component.html',
  styleUrl: './profile-chat.component.scss',
})
export class ProfileChatComponent implements OnInit, AfterViewChecked {
  private profiles = inject(ProfileService);
  private snack = inject(MatSnackBar);
  private router = inject(Router);

  @ViewChild('scroller') scroller?: ElementRef<HTMLElement>;

  readonly profile = this.profiles.profile;
  turns = signal<Turn[]>([]);
  draft = '';
  sending = signal(false);
  loading = signal(true);

  readonly completeness = computed(() => this.profile()?.completeness ?? 0);
  readonly missing = computed(() => this.profile()?.missing ?? []);

  private shouldScroll = false;

  ngOnInit(): void {
    this.profiles.load().subscribe({
      next: (p) => {
        this.turns.set(p.conversation as Turn[]);
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

  label(field: string): string {
    return FIELD_LABELS[field] ?? field;
  }

  send(): void {
    const message = this.draft.trim();
    if (!message || this.sending()) return;

    this.draft = '';
    this.sending.set(true);
    this.turns.update((list) => [...list, { role: 'user', content: message }]);
    this.shouldScroll = true;

    this.profiles.send(message).subscribe({
      next: (res) => {
        this.sending.set(false);
        this.turns.update((list) => [
          ...list,
          { role: 'assistant', content: res.reply, noted: res.changed },
        ]);
        this.shouldScroll = true;
      },
      error: (err) => {
        this.sending.set(false);
        // Se devuelve al cuadro de texto para no perder lo escrito.
        this.turns.update((list) => list.slice(0, -1));
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
    this.profiles.resetChat().subscribe({
      next: (p) => {
        this.turns.set(p.conversation as Turn[]);
        this.shouldScroll = true;
        this.snack.open('Conversación reiniciada. Tus datos siguen guardados.', 'OK', {
          duration: 4000,
        });
      },
      error: () => this.snack.open('No se pudo reiniciar', 'OK'),
    });
  }

  finish(): void {
    this.router.navigate(['/profile']);
  }
}
