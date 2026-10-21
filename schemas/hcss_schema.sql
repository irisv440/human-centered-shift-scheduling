--
-- PostgreSQL database dump
--

\restrict XM5TPkDlONcKvZj32aOdVICOFkBzhpWUIlom4tDKR3eq2S6fp0XEqpYIpdMF4Z0

-- Dumped from database version 18.6
-- Dumped by pg_dump version 18.6

-- Started on 2026-10-19 13:45:07

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 221 (class 1259 OID 16458)
-- Name: historical_sleep; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.historical_sleep (
    worker_id character varying(10) NOT NULL,
    sleep_date date NOT NULL,
    linked_shift character varying(10) NOT NULL,
    linked_shift_date date,
    sleep_start timestamp without time zone,
    sleep_end timestamp without time zone,
    sleep_duration_hours double precision,
    sleep_midpoint timestamp without time zone,
    no_main_sleep_episode boolean NOT NULL
);


ALTER TABLE public.historical_sleep OWNER TO postgres;

--
-- TOC entry 220 (class 1259 OID 16398)
-- Name: shift_assignments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.shift_assignments (
    shift_date date NOT NULL,
    worker_id character varying(10) NOT NULL,
    team character varying(10) NOT NULL,
    shift_type character varying(10) NOT NULL,
    shift_start time without time zone,
    shift_end time without time zone,
    cycle_day smallint NOT NULL
);


ALTER TABLE public.shift_assignments OWNER TO postgres;

--
-- TOC entry 222 (class 1259 OID 16480)
-- Name: worker_profiles; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.worker_profiles (
    worker_id character varying(10) NOT NULL,
    sleep_need_hours double precision NOT NULL
);


ALTER TABLE public.worker_profiles OWNER TO postgres;

--
-- TOC entry 219 (class 1259 OID 16389)
-- Name: workers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.workers (
    worker_id character varying(10) NOT NULL,
    role character varying(50) NOT NULL,
    contract_hours_week smallint NOT NULL,
    team character varying(10) NOT NULL
);


ALTER TABLE public.workers OWNER TO postgres;

--
-- TOC entry 4872 (class 2606 OID 16474)
-- Name: historical_sleep historical_sleep_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.historical_sleep
    ADD CONSTRAINT historical_sleep_pkey PRIMARY KEY (worker_id, sleep_date);


--
-- TOC entry 4870 (class 2606 OID 16407)
-- Name: shift_assignments shift_assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shift_assignments
    ADD CONSTRAINT shift_assignments_pkey PRIMARY KEY (shift_date, worker_id);


--
-- TOC entry 4874 (class 2606 OID 16486)
-- Name: worker_profiles worker_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.worker_profiles
    ADD CONSTRAINT worker_profiles_pkey PRIMARY KEY (worker_id);


--
-- TOC entry 4868 (class 2606 OID 16397)
-- Name: workers workers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.workers
    ADD CONSTRAINT workers_pkey PRIMARY KEY (worker_id);


--
-- TOC entry 4876 (class 2606 OID 16475)
-- Name: historical_sleep historical_sleep_worker_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.historical_sleep
    ADD CONSTRAINT historical_sleep_worker_id_fkey FOREIGN KEY (worker_id) REFERENCES public.workers(worker_id);


--
-- TOC entry 4875 (class 2606 OID 16408)
-- Name: shift_assignments shift_assignments_worker_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shift_assignments
    ADD CONSTRAINT shift_assignments_worker_id_fkey FOREIGN KEY (worker_id) REFERENCES public.workers(worker_id);


--
-- TOC entry 4877 (class 2606 OID 16487)
-- Name: worker_profiles worker_profiles_worker_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.worker_profiles
    ADD CONSTRAINT worker_profiles_worker_id_fkey FOREIGN KEY (worker_id) REFERENCES public.workers(worker_id);


-- Completed on 2026-10-19 13:45:08

--
-- PostgreSQL database dump complete
--

\unrestrict XM5TPkDlONcKvZj32aOdVICOFkBzhpWUIlom4tDKR3eq2S6fp0XEqpYIpdMF4Z0

