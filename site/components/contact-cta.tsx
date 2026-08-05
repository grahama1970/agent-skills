'use client';

import { ButtonLink } from '@/components/ui/button';
import { useRegisterAction } from '@/lib/use-register-action';

export function ContactCta() {
  useRegisterAction('contact:action:email', {
    app: 'grahama-labs-site',
    action: 'CONTACT_EMAIL',
    label: 'Email Graham',
    description: 'Open a mail draft to graham@grahama.co',
  });

  return (
    <ButtonLink
      href="mailto:graham@grahama.co"
      data-qid="contact:action:email"
      data-qs-action="CONTACT_EMAIL"
      title="Email graham@grahama.co"
      className="mt-2"
    >
      email graham@grahama.co
    </ButtonLink>
  );
}
