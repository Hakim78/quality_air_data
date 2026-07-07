-- referentiel des polluants mesures par les capteurs de particules
-- seuils oms 2021 en moyenne 24h, pas de seuil publie pour les pm1
INSERT INTO gold.dim_polluant (code_api, libelle, seuil_oms_24h) VALUES
    ('P0', 'PM1',   NULL),
    ('P1', 'PM10',  45),
    ('P2', 'PM2.5', 15)
ON CONFLICT (code_api) DO NOTHING;
