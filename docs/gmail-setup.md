# Configuración de Gmail

CandiTrack lee tu correo con la [Gmail API](https://developers.google.com/gmail/api) usando
OAuth y el permiso **`gmail.readonly`** (solo lectura: no puede enviar, borrar ni modificar correos).

Todo lo que se describe aquí es **gratuito** y no necesita facturación.

## 1. Crear el proyecto en Google Cloud

1. Entra en <https://console.cloud.google.com/> con la cuenta de Gmail que quieres conectar.
2. Selector de proyectos (arriba a la izquierda) → **New Project** → nombre `CandiTrack` → **Create**.
3. Asegúrate de que **CandiTrack** está seleccionado arriba.

### Evitar cargos

La Gmail API no tiene coste, pero por seguridad deja el proyecto **sin facturación vinculada**:

- ☰ → **Billing**. Si el proyecto aparece vinculado a una cuenta de facturación:
  **Account management** → fila de CandiTrack → ⋮ → **Disable billing**.
- No actives servicios de pago (Compute Engine, Cloud Run, Cloud SQL, Vertex AI...).

## 2. Activar la Gmail API

Buscador superior → **Gmail API** → **Enable**.

## 3. Configurar Google Auth Platform (pantalla de consentimiento)

Buscador superior → **Google Auth Platform** (u *OAuth consent screen*) → **Get started**:

| Pantalla            | Valor                                   |
|---------------------|-----------------------------------------|
| App name            | `CandiTrack`                            |
| User support email  | tu Gmail                                |
| Audience            | **External**                            |
| Contact information | tu Gmail                                |

Acepta la política → **Create**.

Después, en el menú lateral → **Audience**:

- **Publishing status** debe quedarse en **Testing** (no pulses *Publish app*).
- **Test users** → **+ Add users** → añade tu Gmail → **Save**.
  Sin esto Google bloqueará la autorización.

## 4. Crear las credenciales (`credentials.json`)

1. Menú lateral → **Clients** → **+ Create client**.
2. **Application type**: `Desktop app` · **Name**: `CandiTrack CLI` → **Create**.
3. **Download JSON** (hazlo en ese momento: Google no permite volver a descargar el secreto).
4. Renómbralo a `credentials.json` y colócalo en la raíz del proyecto.

> ⚠️ `credentials.json` y `token.json` son secretos. Están en `.gitignore`: **nunca** los subas
> al repositorio ni los compartas.

## 5. Primera ejecución

```bash
uv run canditrack fetch
```

La primera vez se abrirá el navegador para autorizar el acceso. Como la app no está verificada
por Google, verás un aviso: **Advanced → Go to CandiTrack (unsafe)** → **Continue**.
Es normal: la app es tuya.

Tras autorizar se crea `token.json` y las siguientes ejecuciones no piden nada.

Opciones útiles:

```bash
uv run canditrack fetch -q "newer_than:30d subject:candidatura" -n 20
```

`-q` acepta la misma sintaxis que el buscador de Gmail.

## Notas

- **El token caduca cada 7 días** mientras la app esté en modo *Testing*. CandiTrack lo detecta
  y vuelve a abrir el navegador para autorizar; no hay que hacer nada más.
- Publicar la app para otros usuarios con `gmail.readonly` requiere una verificación de
  seguridad de Google (de pago). Para uso personal no es necesario.
- Para revocar el acceso: <https://myaccount.google.com/permissions> → CandiTrack → *Remove access*.
