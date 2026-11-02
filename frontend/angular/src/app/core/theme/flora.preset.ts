import { definePreset } from '@primeuix/themes';
import Aura from '@primeuix/themes/aura';

const FloraPreset = definePreset(Aura, {
  primitive: {
    flora: {
      50: '#F3FAF8',
      100: '#D7EBE7',
      200: '#B3D6D0',
      300: '#7FB8AE',
      400: '#3E8F84',
      500: '#155E53',
      600: '#114E45',
      700: '#0E3F38',
      800: '#0C322C',
      900: '#09241F',
      950: '#051614'
    }
  },
  semantic: {
    primary: {
      50: '{flora.50}',
      100: '{flora.100}',
      200: '{flora.200}',
      300: '{flora.300}',
      400: '{flora.400}',
      500: '{flora.500}',
      600: '{flora.600}',
      700: '{flora.700}',
      800: '{flora.800}',
      900: '{flora.900}',
      950: '{flora.950}'
    },
    colorScheme: {
      light: {
        surface: {
          0: '#FFFFFF',
          50: '#F8FAF9',
          100: '#F1F5F3',
          200: '#DCE5E1',
          300: '#C9D6D0',
          400: '#8FA099',
          500: '#64736E',
          600: '#4E5E58',
          700: '#22332F',
          800: '#1B2926',
          900: '#14211E',
          950: '#0E1714'
        }
      },
      dark: {
        surface: {
          0: '#E7F0EC',
          50: '#D5E4DE',
          100: '#B7CBC3',
          200: '#8FA39B',
          300: '#6E847C',
          400: '#9AABA4',
          500: '#6E847C',
          600: '#3E534C',
          700: '#2A3C36',
          800: '#1B2B26',
          900: '#101A17',
          950: '#0B1210'
        },
        primary: {
          color: '{flora.300}',
          contrastColor: '#0E1714',
          hoverColor: '{flora.200}',
          activeColor: '{flora.100}'
        },
        highlight: {
          background: 'color-mix(in srgb, {flora.300}, transparent 84%)',
          focusBackground: 'color-mix(in srgb, {flora.300}, transparent 76%)',
          color: '{flora.100}',
          focusColor: '#FFFFFF'
        }
      }
    }
  }
});

export default FloraPreset;
