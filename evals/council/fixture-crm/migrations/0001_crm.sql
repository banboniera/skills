-- Workshop CRM schema. Every table is tenant-scoped by company_id.

CREATE TABLE companies (
  id uuid PRIMARY KEY,
  name text NOT NULL
);

CREATE TABLE users (
  id uuid PRIMARY KEY,
  phone text NOT NULL UNIQUE,
  full_name text NOT NULL
);

-- The workshop's card for one of its customers. Not a login.
CREATE TABLE customers (
  company_id uuid NOT NULL REFERENCES companies(id),
  id uuid NOT NULL,
  full_name text NOT NULL,
  phone text NOT NULL,
  email text,
  note text,
  deleted_at timestamptz,
  PRIMARY KEY (company_id, id)
);

-- Invoice identities of a customer: a private person may invoice as several firms.
CREATE TABLE customer_billing_profiles (
  company_id uuid NOT NULL,
  id uuid NOT NULL,
  customer_id uuid NOT NULL,
  tax_id text,
  name text NOT NULL,
  address text NOT NULL,
  is_default boolean NOT NULL DEFAULT false,
  deleted_at timestamptz,
  PRIMARY KEY (company_id, id),
  FOREIGN KEY (company_id, customer_id) REFERENCES customers(company_id, id)
);
CREATE UNIQUE INDEX customer_billing_profiles_tax_id_key
  ON customer_billing_profiles (company_id, customer_id, tax_id) WHERE deleted_at IS NULL;

CREATE TABLE company_vehicles (
  company_id uuid NOT NULL,
  id uuid NOT NULL,
  customer_id uuid NOT NULL,
  vin text NOT NULL,
  license_plate text,
  PRIMARY KEY (company_id, id),
  FOREIGN KEY (company_id, customer_id) REFERENCES customers(company_id, id)
);

-- An SMS invitation to a phone number; once accepted it grants a users account
-- access to the customer record in the customer app.
CREATE TYPE access_scope AS ENUM ('full', 'vehicles');
CREATE TABLE customer_access (
  company_id uuid NOT NULL,
  id uuid NOT NULL,
  customer_id uuid NOT NULL,
  phone text NOT NULL,
  access_scope access_scope NOT NULL,
  can_manage boolean NOT NULL DEFAULT false,
  invited_by uuid NOT NULL REFERENCES users(id),
  issued_by_access_id uuid,
  accepted_by uuid REFERENCES users(id),
  accepted_at timestamptz,
  revoked_at timestamptz,
  expires_at timestamptz NOT NULL,
  PRIMARY KEY (company_id, id),
  FOREIGN KEY (company_id, customer_id) REFERENCES customers(company_id, id),
  FOREIGN KEY (company_id, issued_by_access_id) REFERENCES customer_access(company_id, id),
  CHECK (NOT can_manage OR access_scope = 'full'),
  CHECK ((accepted_by IS NULL) = (accepted_at IS NULL))
);
CREATE UNIQUE INDEX customer_access_live_key
  ON customer_access (company_id, customer_id, accepted_by)
  WHERE revoked_at IS NULL AND accepted_by IS NOT NULL;

-- Cars a 'vehicles'-scoped access may see. Frozen once the invitation is accepted.
CREATE TABLE customer_access_vehicles (
  company_id uuid NOT NULL,
  access_id uuid NOT NULL,
  company_vehicle_id uuid NOT NULL,
  PRIMARY KEY (company_id, access_id, company_vehicle_id),
  FOREIGN KEY (company_id, access_id) REFERENCES customer_access(company_id, id),
  FOREIGN KEY (company_id, company_vehicle_id) REFERENCES company_vehicles(company_id, id)
);

CREATE TABLE service_orders (
  company_id uuid NOT NULL,
  id uuid NOT NULL,
  customer_id uuid,
  company_vehicle_id uuid,
  contact_name text,
  contact_phone text,
  status text NOT NULL,
  PRIMARY KEY (company_id, id),
  FOREIGN KEY (company_id, customer_id) REFERENCES customers(company_id, id)
);
