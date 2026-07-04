# Kimlik Doğrulama ve Yetkilendirme

Bu doküman, IK Platform'un login, oturum, JWT, refresh token, MFA, RBAC, scope ve field-level permission tasarımını tanımlar.

## 1. Tasarım hedefleri

| Hedef | Karar |
|---|---|
| Güvenli login | Tenant-aware e-posta/şifre ve MFA hazırlığı |
| Kısa ömürlü access | Access token kısa süreli olmalı |
| Merkezi revoke | Refresh token ve session server-side izlenmeli |
| Tenant izolasyonu | JWT/session tenant context taşır |
| İnce yetki | RBAC + scope + field-level permission |
| Enterprise uyum | SAML/OIDC/SCIM hazırlığı |

## 2. Login sistemi

| Konu | Karar |
|---|---|
| Tenant bazlı giriş | Subdomain, kurum kodu veya e-posta domain discovery |
| E-posta unique | Tenant içinde unique, global unique zorunlu değil |
| Şifre hash | Argon2id veya eşdeğer güçlü hash |
| Şifre politikası | Minimum uzunluk, sızmış parola kontrolü V1 |
| Rate limit | IP + tenant + e-posta bazlı |
| Şifre sıfırlama | Tek kullanımlık, kısa ömürlü, hashli token |
| İlk aktivasyon | Davet linki veya alternatif mavi yaka aktivasyon akışı |

## 3. Token ve session mimarisi

| Token | Süre | Saklama | Amaç |
|---|---:|---|---|
| Access token | 10-15 dk | Web cookie/BFF veya memory | API erişimi |
| Refresh token | 7-30 gün | HttpOnly cookie / secure storage | Yenileme |
| MFA challenge | 5 dk | Geçici | MFA doğrulama |
| Password reset | 15 dk | DB hash | Şifre sıfırlama |
| SSO state/nonce | 5 dk | Server cache | SSO güvenliği |

Refresh token rotation zorunludur. Kullanılmış token tekrar gelirse aynı token family revoke edilir.

## 4. JWT claim yapısı

```json
{
  "sub": "user_id",
  "tenant_id": "tenant_id",
  "roles": ["hr_specialist"],
  "scopes": ["tenant"],
  "session_id": "session_id",
  "device_id": "device_id",
  "mfa": true,
  "iat": 1783070000,
  "exp": 1783070900,
  "jti": "jwt_id"
}
```

Token boyutu büyürse permission listesi token içine gömülmez; `permission_version` claim'iyle server-side çözülür.

## 5. Web ve mobil saklama

| Client | Access | Refresh | Kontrol |
|---|---|---|---|
| Web BFF | JS'e verilmez | HttpOnly Secure cookie | CSRF/origin kontrolü |
| Web SPA | Memory | HttpOnly cookie | CSP ve XSS sertleştirme |
| Mobil | Memory | Keychain/Keystore | Biyometri/step-up |
| API client | OAuth/client credentials | Rotation veya PAT | IP allowlist/scope |

## 6. RBAC rolleri

| Rol | Temel izinler |
|---|---|
| `employee` | `employee:read:own`, `leave:create:own`, `document:read:own` |
| `manager` | `employee:read:team`, `leave:approve:team`, `request:approve:team` |
| `hr_specialist` | `employee:manage:tenant`, `document:manage:tenant`, `leave:manage:tenant` |
| `payroll_specialist` | `payroll:manage:tenant`, `employee:read:payroll_fields` |
| `tenant_admin` | `tenant:update`, `role:manage`, `user:manage` |
| `auditor` | `audit:read:tenant`, read-only reports |
| `super_admin` | Platform ops; müşteri verisine break-glass dışında erişmez |

## 7. Scope modeli

| Scope | Kullanım |
|---|---|
| `own` | Kendi kaydı |
| `team` | Yönetici olduğu ekip |
| `department` | Departman kapsamı |
| `branch` | Şube/lokasyon kapsamı |
| `tenant` | Tüm kurum |
| `global` | Platform operasyonu |

## 8. Field-level permission

| Alan | Sınıf | Varsayılan |
|---|---|---|
| TCKN/YKN | Sensitive PII | Maskeli |
| IBAN | Sensitive financial | Maskeli |
| Maaş | Sensitive financial | Gizli/maskeli |
| Sağlık raporu | Special category | Gizli |
| Performans skoru | Sensitive HR | Scope + permission |
| AI skor | Profiling | Açıklama + review |

Field policy sonuçları:

- `allow`
- `mask`
- `deny`
- `step_up`

## 9. Delegasyon, geçici rol ve break-glass

| Mekanizma | Kural |
|---|---|
| Delegasyon | Süreli, kapsamlı, auditli |
| Geçici rol | Başlangıç/bitiş tarihi ve gerekçe ister |
| Vekalet | Kritik alanlarda ikinci onay gerekebilir |
| Break-glass | Müşteri onayı, süreli erişim, otomatik kapanış, tam audit |

## 10. Enterprise SSO

V1/Enterprise kapsamı:

- OIDC.
- SAML 2.0.
- Entra ID/Okta/Keycloak mapping.
- Group → role mapping.
- SCIM provisioning Enterprise.

MVP'de SSO-ready veri modeli ve claim mapping yaklaşımı düşünülür, tam uygulama ertelenir.

## 11. Kabul kriterleri

- Login tenant-aware çalışır.
- Refresh token rotation ve reuse detection vardır.
- Tenant mismatch istekleri reddedilir.
- Own/team/tenant scope testleri geçer.
- Hassas alanlar permission olmadan tam görünmez.
- Rol değişiklikleri auditlenir.
- Admin/payroll/export işlemleri step-up destekler.

## 12. İlgili dokümanlar

- [CORE, AUTH ve RBAC Modülleri](../03-moduller/01-core-auth-rbac.md)
- [Çok Kiracılık ve Veri İzolasyonu](../04-mimari/02-cok-kiracilik-ve-veri-izolasyonu.md)
- [API Standartları, OpenAPI ve Webhook](../05-api-veri/02-api-standartlari-openapi-webhook.md)
